import os,json,time,warnings
from pathlib import Path
os.environ['HF_HUB_OFFLINE']='1'
import torch,numpy as np,onnxruntime as ort
from transformers import VitsModel,VitsTokenizer
ROOT=Path(__file__).resolve().parent
torch.set_num_threads(2)
class Export(torch.nn.Module):
    def __init__(self,m):super().__init__();self.m=m
    def forward(self,ids):return self.m(ids).waveform
for name in ('orm','tir','som'):
    folder=ROOT/('mms-'+name)
    if not (folder/'model.safetensors').exists():continue
    start=time.perf_counter()
    try:
        model=VitsModel.from_pretrained(folder,local_files_only=True).eval()
        tokenizer=VitsTokenizer.from_pretrained(folder,local_files_only=True)
        tokens=tokenizer('Hello world',return_tensors='pt')['input_ids']
        target=folder/'model.onnx'
        if not target.exists():
            with torch.no_grad(),warnings.catch_warnings():
                warnings.simplefilter('ignore')
                torch.onnx.export(Export(model),tokens,str(target),input_names=['input_ids'],output_names=['waveform'],dynamic_axes={'input_ids':{1:'text_length'},'waveform':{1:'audio_length'}},opset_version=17,dynamo=False)
        opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
        session=ort.InferenceSession(str(target),sess_options=opts,providers=['CPUExecutionProvider'])
        checks=[]
        for text in ['Akkam jirtu?','Silav, tu çawa yî?','This is a longer phrase with several words and different lengths.']:
            ids=tokenizer(text,return_tensors='np')['input_ids'];t=time.perf_counter();wav=session.run(None,{'input_ids':ids})[0]
            checks.append({'characters':len(text),'audio_seconds':wav.size/model.config.sampling_rate,'seconds':time.perf_counter()-t,'finite':bool(np.isfinite(wav).all())})
        report={'model':name,'bytes':target.stat().st_size,'seconds':time.perf_counter()-start,'checks':checks}
    except Exception as e:report={'model':name,'error':repr(e)}
    (folder/'export-result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
