<p align="center">![images](https://github.com/user-attachments/assets/1a8ba455-72fd-447a-ae58-48933497c3a4)</p> 

这个Repo的由来是因为我在安装ComfyUI插件ComfyUI-LTXVideo过程中，发现它的文生视频Workflow在访问https://huggingface.co时会出错，于是我将代码进行了修改，将访问https://huggingface.co改为其镜像站点https://hf-mirror.com/。接着在工作流中运行文生视频，发现我的3060 12GB显卡经常OOM，于是我爆改了prompt_enhancer_nodes.py和prompt_enhancer_utils.py这两个文件，经测试终于可以顺利的使用ComfyUI-LTXVideo的所有工作流。因为ComfyUI-LTXVideo生成视频的速度非常快，我觉得是一个非常好的工具，也许有人需要吧，所以我就将其共享出来。
在此感谢https://github.com/Lightricks/ComfyUI-LTXVideo的开源插件ComfyUI-LTXVideo，感谢https://github.com/comfyanonymous/ComfyUI开源ComfyUI。
