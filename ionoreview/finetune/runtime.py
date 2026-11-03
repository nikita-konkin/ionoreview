"""Assistant-only multimodal SFT, with explicit sequence and GPU limits."""
import json
from pathlib import Path

from PIL import Image

from ..data import atomic_json,read_json,utcnow
from .common import snapshot,rows,gpu_lease,require_gpu


def processor_for(cfg):
    from transformers import AutoProcessor
    processor=AutoProcessor.from_pretrained(str(snapshot(cfg)),local_files_only=True,
        size={'shortest_edge':65536,'longest_edge':cfg['max_pixels_per_image']})
    processor.tokenizer.padding_side='right'
    return processor


def prompt_text(processor,row):
    messages=[{'role':'user','content':[{'type':'image'},{'type':'image'},
        {'type':'text','text':row['prompt']}]}]
    return processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)


class Collator:
    def __init__(self,processor,folder,max_length):
        self.processor=processor;self.folder=Path(folder);self.max_length=max_length

    def __call__(self,examples):
        import torch
        prompts=[];texts=[];images=[]
        for row in examples:
            prompt=prompt_text(self.processor,row);prompts.append(prompt)
            target=json.dumps(row['target'],separators=(',',':'),ensure_ascii=True)
            texts.append(prompt+target+self.processor.tokenizer.eos_token)
            loaded=[]
            for relative in row['images']:
                from ..data import safe_child
                with Image.open(safe_child(self.folder,relative)) as image:loaded.append(image.convert('RGB'))
            images.extend(loaded)
        arguments={'images':images,'padding':True,'return_tensors':'pt','add_special_tokens':False}
        batch=self.processor(text=texts,**arguments)
        prefixes=self.processor(text=prompts,**arguments)
        labels=batch['input_ids'].clone()
        for index in range(len(examples)):
            full_len=int(batch['attention_mask'][index].sum())
            prompt_len=int(prefixes['attention_mask'][index].sum())
            if full_len>self.max_length:
                raise ValueError(f"{examples[index]['id']}: {full_len} tokens exceeds {self.max_length}; no truncation was applied")
            if not torch.equal(batch['input_ids'][index,:prompt_len],prefixes['input_ids'][index,:prompt_len]):
                raise ValueError('Prompt/answer token boundary changed; refusing an invalid loss mask')
            labels[index,:prompt_len]=-100
            labels[index,full_len:]=-100
            if not (labels[index]!=-100).any():raise ValueError('No assistant target tokens')
        batch['labels']=labels
        return batch


def inspect_data(cfg,folder):
    processor=processor_for(cfg);collator=Collator(processor,folder,cfg['max_seq_length'])
    report={'checked_at':utcnow(),'model':cfg['model_id'],'revision':cfg['model_revision'],'splits':{}}
    report['preprocessing']={k:cfg[k] for k in ['max_seq_length','max_pixels_per_image']}
    errors=[]
    for split in ['train','validation','test']:
        lengths=[];targets=[]
        for row in rows(folder,split):
            try:
                batch=collator([row]);lengths.append(int(batch['attention_mask'].sum()))
                targets.append(int((batch['labels']!=-100).sum()))
            except ValueError as exc:errors.append({'id':row['id'],'split':split,'error':str(exc)})
        report['splits'][split]={'examples':len(lengths),'max_tokens':max(lengths,default=0),
            'max_target_tokens':max(targets,default=0)}
    report['errors']=errors
    atomic_json(Path(folder)/'tokenization_report.json',report)
    if errors:raise ValueError(f'{len(errors)} examples failed; see tokenization_report.json. No examples were silently dropped.')
    return report


def lora_config(cfg):
    from peft import LoraConfig
    # Vision attention uses qkv/proj, not these text decoder projection names.
    return LoraConfig(r=cfg['lora_rank'],lora_alpha=cfg['lora_alpha'],lora_dropout=.05,
        target_modules=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'],
        bias='none',task_type='CAUSAL_LM')


def load_model(cfg,training=False,adapter=None):
    import torch
    from transformers import Qwen3_5ForConditionalGeneration,BitsAndBytesConfig
    from peft import get_peft_model,prepare_model_for_kbit_training,PeftModel
    kwargs={'local_files_only':True,'dtype':torch.bfloat16,'device_map':{'':'cuda:0'},'attn_implementation':'sdpa'}
    if cfg['quantization']=='nf4':
        kwargs['quantization_config']=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16,
            llm_int8_skip_modules=['visual','lm_head','mtp'])
    elif cfg['quantization']!='bf16':raise ValueError('quantization must be nf4 or bf16')
    model=Qwen3_5ForConditionalGeneration.from_pretrained(str(snapshot(cfg)),**kwargs)
    model.config.use_cache=not training
    model.config.text_config.use_cache=not training
    if adapter is not None:
        model=PeftModel.from_pretrained(model,str(adapter),is_trainable=False)
    elif training:
        if cfg['quantization']=='nf4':model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True,
            gradient_checkpointing_kwargs={'use_reentrant':False})
        else:
            model.requires_grad_(False)
            model.enable_input_require_grads()
            model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        model=get_peft_model(model,lora_config(cfg))
        trainable=[name for name,p in model.named_parameters() if p.requires_grad]
        if not trainable or any('visual' in name or 'lora_' not in name for name in trainable):
            raise ValueError('Unexpected trainable parameters; expected only text-decoder LoRA')
    return model


def train(cfg,folder,name,max_steps=None):
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',name):raise ValueError('Invalid run name')
    import torch
    from transformers import Trainer,TrainingArguments,set_seed,TrainerCallback
    folder=Path(folder).resolve();report=read_json(folder/'tokenization_report.json')
    if report['errors']:raise ValueError('Tokenization errors must be resolved first')
    if report['revision']!=cfg['model_revision']:raise ValueError('Tokenizer/model revision changed')
    if report.get('preprocessing')!={k:cfg[k] for k in ['max_seq_length','max_pixels_per_image']}:
        raise ValueError('Preprocessing changed; run inspect again')
    run=Path(cfg['run_root'])/name
    if run.exists():raise ValueError('Run already exists; choose a new name (existing adapters are preserved)')
    with gpu_lease(cfg,'ionoreview-finetune'):
        gpu=require_gpu(cfg,training=True)
        set_seed(cfg['seed'])
        processor=processor_for(cfg);model=load_model(cfg,training=True)
        class Examples(torch.utils.data.Dataset):
            def __init__(self,split):self.data=rows(folder,split)
            def __len__(self):return len(self.data)
            def __getitem__(self,index):return self.data[index]
        class Progress(TrainerCallback):
            def on_log(self,args,state,control,logs=None,**kwargs):
                atomic_json(run/'progress.json',{'updated_at':utcnow(),'step':state.global_step,
                    'max_steps':state.max_steps,'logs':logs or {}})
        args=TrainingArguments(output_dir=str(run),num_train_epochs=cfg['epochs'],
            max_steps=max_steps if max_steps is not None else -1,learning_rate=cfg['learning_rate'],
            per_device_train_batch_size=1,per_device_eval_batch_size=1,
            gradient_accumulation_steps=cfg['gradient_accumulation_steps'],
            bf16=True,gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False},
            optim='adamw_torch',logging_steps=1,eval_strategy='epoch',save_strategy='epoch',
            save_total_limit=2,load_best_model_at_end=True,metric_for_best_model='eval_loss',
            greater_is_better=False,remove_unused_columns=False,dataloader_num_workers=0,
            dataloader_pin_memory=False,report_to=[],seed=cfg['seed'],warmup_steps=0 if max_steps==1 else .05)
        trainer=Trainer(model=model,args=args,train_dataset=Examples('train'),eval_dataset=Examples('validation'),
            data_collator=Collator(processor,folder,cfg['max_seq_length']),callbacks=[Progress()])
        run.mkdir(parents=True,exist_ok=True)
        atomic_json(run/'run.json',{'started_at':utcnow(),'config':cfg,'dataset':str(folder),
            'dataset_fingerprint':read_json(folder/'report.json')['fingerprint'],'gpu':gpu,
            'max_steps':max_steps,'scope':'experimental pilot; no test examples used for training'})
        try:
            outcome=trainer.train()
            trainer.save_model(str(run/'adapter'));processor.save_pretrained(run/'adapter')
            atomic_json(run/'finished.json',{'finished_at':utcnow(),'metrics':outcome.metrics,
                'best_checkpoint':trainer.state.best_model_checkpoint,'adapter':str(run/'adapter')})
        except Exception as exc:
            atomic_json(run/'failed.json',{'failed_at':utcnow(),'type':type(exc).__name__,'error':str(exc)})
            raise
    return {'run':str(run),'adapter':str(run/'adapter')}


def merge_adapter(cfg,adapter,out):
    import torch
    from transformers import Qwen3_5ForConditionalGeneration
    from peft import PeftModel
    out=Path(out)
    if out.exists():raise ValueError('Output directory exists')
    model=Qwen3_5ForConditionalGeneration.from_pretrained(str(snapshot(cfg)),local_files_only=True,
        dtype=torch.bfloat16,device_map={'':'cpu'})
    model=PeftModel.from_pretrained(model,str(adapter)).merge_and_unload(safe_merge=True)
    model.save_pretrained(out,safe_serialization=True,max_shard_size='2GB')
    processor_for(cfg).save_pretrained(out)
    return {'merged_hf':str(out.resolve()),'includes_vision':True,
            'note':'This is a Hugging Face model, not a GGUF file. The inference MCP can use the original base plus adapter directly.'}
