.<div align=center><img src="https://github.com/user-attachments/assets/1a8ba455-72fd-447a-ae58-48933497c3a4" width="246" height="205" /></div>

**这个Repo的由来是因为我在安装ComfyUI插件ComfyUI-LTXVideo过程中，发现我的3060 12GB显卡经常OOM，于是我爆改了prompt_enhancer_nodes.py和prompt_enhancer_utils.py这两个文件，  
经测试终于可以顺利的使用ComfyUI-LTXVideo的所有工作流。因为ComfyUI-LTXVideo生成视频的速度非常快，我觉得是一个非常好的工具，也许有人需要吧，所以我就将其共享出来。  
在此感谢[Lightricks](https://github.com/Lightricks/ComfyUI-LTXVideo)的开源插件ComfyUI-LTXVideo  
感谢[comfyanonymous](https://github.com/comfyanonymous/ComfyUI)开源ComfyUI。**  

**如果你在运行ComfyUI-LTXVideo工作流时出现不能访问[huggingface](https://huggingface.co/),你可以在运行工作流前按下面的方法操作**  
'''python
pip install -U huggingface_hub  
export HF_ENDPOINT=https://hf-mirror.com  '''
如果你要手动下载unsloth/Llama-3.2-3B-Instruct和MiaoshouAI/Florence-2-large-PromptGen-v2.0,请下载到Models/LLM目录下面

