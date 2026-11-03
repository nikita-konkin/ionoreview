import importlib.metadata
import json
from pathlib import Path
import subprocess

from ..data import atomic_json,utcnow
from .common import PROJECT,snapshot,gpu_lease


def tiny_backward(cfg):
    """Two-layer version of the same multimodal architecture, on CPU."""
    import torch
    from transformers import Qwen3_5Config,Qwen3_5ForConditionalGeneration
    from peft import get_peft_model
    from .runtime import lora_config
    original_threads=torch.get_num_threads();torch.set_num_threads(2)
    try:
        text={'hidden_size':64,'intermediate_size':128,'num_hidden_layers':2,
            'num_attention_heads':4,'num_key_value_heads':2,'head_dim':16,'vocab_size':256,
            'layer_types':['linear_attention','full_attention'],'full_attention_interval':2,
            'linear_num_key_heads':2,'linear_num_value_heads':2,'linear_key_head_dim':16,
            'linear_value_head_dim':16,'linear_conv_kernel_dim':4,
            'rope_parameters':{'rope_type':'default','rope_theta':10000.,'partial_rotary_factor':1.,
                'mrope_section':[2,3,3],'mrope_interleaved':True}}
        vision={'hidden_size':32,'intermediate_size':64,'out_hidden_size':64,'depth':1,
            'num_heads':4,'patch_size':16,'temporal_patch_size':2,'spatial_merge_size':2,
            'num_position_embeddings':64,'deepstack_visual_indexes':[]}
        model=Qwen3_5ForConditionalGeneration(Qwen3_5Config(text_config=text,vision_config=vision,
            image_token_id=253,video_token_id=254,vision_start_token_id=250,vision_end_token_id=251))
        model=get_peft_model(model,lora_config(cfg));model.train()
        ids=torch.tensor([[10,250,253,251,11,250,253,251,12,13,14,15]])
        labels=ids.clone();labels[:,:8]=-100
        before={n:p.detach().clone() for n,p in model.named_parameters() if p.requires_grad}
        optim=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.01)
        output=model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=labels,
            pixel_values=torch.randn(8,1536),image_grid_thw=torch.tensor([[1,2,2],[1,2,2]]),
            mm_token_type_ids=(ids==253).long(),use_cache=False)
        if not torch.isfinite(output.loss):raise ValueError('Tiny-model loss is not finite')
        output.loss.backward();optim.step()
        changed=sum(not torch.equal(before[n],p.detach()) for n,p in model.named_parameters() if n in before)
        if not changed:raise ValueError('LoRA parameters did not update')
        return {'ok':True,'loss':float(output.loss.detach()),'updated_lora_tensors':changed,
                'scope':'CPU tiny architecture only; not a real pilot training run'}
    finally:torch.set_num_threads(original_threads)


def doctor(cfg,cuda_smoke=False,load_cpu=False):
    import torch
    report={'checked_at':utcnow(),'model_id':cfg['model_id'],'revision':cfg['model_revision'],
        'packages':{},'cuda_available':torch.cuda.is_available(),'training_started':False}
    for package in ['torch','torchvision','transformers','peft','accelerate','bitsandbytes','shapely','mcp']:
        report['packages'][package]=importlib.metadata.version(package)
    path=snapshot(cfg);report['snapshot']=str(path)
    index=json.loads((path/'model.safetensors.index.json').read_text(encoding='utf8'))
    files=sorted(set(index['weight_map'].values()))
    if any(not (path/f).is_file() for f in files):raise ValueError('Model weights are incomplete')
    report['weight_files']=files;report['weight_bytes']=sum((path/f).stat().st_size for f in files)
    if torch.cuda.is_available():
        free,total=torch.cuda.mem_get_info();report['gpu']={'name':torch.cuda.get_device_name(),
            'free_gib':free/1024**3,'total_gib':total/1024**3,'capability':list(torch.cuda.get_device_capability())}
        report['ready_for_training']=free/1024**3>=cfg['min_train_vram_gib']
    else:report['ready_for_training']=False
    report['tiny_backward']=tiny_backward(cfg)
    if cuda_smoke:
        import bitsandbytes as bnb
        with gpu_lease(cfg,'ionoreview-cuda-smoke'):
            layer=bnb.nn.Linear4bit(16,16,bias=False,compute_dtype=torch.bfloat16,quant_type='nf4').cuda()
            x=torch.randn(2,16,device='cuda',dtype=torch.bfloat16,requires_grad=True)
            loss=layer(x).float().square().mean();loss.backward()
            if not torch.isfinite(x.grad).all():raise ValueError('4-bit CUDA gradients are invalid')
            torch.cuda.synchronize()
            report['cuda_nf4_backward']={'ok':True,'loss':float(loss.detach())}
            del x,layer,loss;torch.cuda.empty_cache()
    if load_cpu:
        from transformers import Qwen3_5ForConditionalGeneration
        from peft import get_peft_model
        from .runtime import lora_config
        model=Qwen3_5ForConditionalGeneration.from_pretrained(str(path),local_files_only=True,
            dtype=torch.bfloat16,device_map={'':'cpu'},attn_implementation='sdpa')
        model=get_peft_model(model,lora_config(cfg))
        trainable=[n for n,p in model.named_parameters() if p.requires_grad]
        if not trainable or any('visual' in n or 'lora_' not in n for n in trainable):raise ValueError('LoRA scope mismatch')
        report['real_weights_cpu_load']={'ok':True,'trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad),
            'total_parameters':sum(p.numel() for p in model.parameters())}
        del model
    atomic_json(PROJECT/'training/reports/doctor.json',report)
    return report
