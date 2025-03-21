import os
import shutil
import comfy.model_management
import comfy.model_patcher
import folder_paths
import torch
from transformers import AutoModelForCausalLM, AutoProcessor, AutoTokenizer
from .nodes_registry import comfy_node
from .prompt_enhancer_utils import generate_cinematic_prompt

# 检查是否支持 4-bit 量化
try:
    from bitsandbytes.nn import Linear4bit
except ImportError:
    Linear4bit = None

LLM_NAME = ["unsloth/Llama-3.2-3B-Instruct"]
IMAGE_CAPTIONER = ["MiaoshouAI/Florence-2-large-PromptGen-v2.0"]
MODELS_PATH_KEY = "LLM"

class PromptEnhancer(torch.nn.Module):
    def __init__(
        self,
        image_caption_processor: AutoProcessor,
        image_caption_model: AutoModelForCausalLM,
        llm_model: AutoModelForCausalLM,
        llm_tokenizer: AutoTokenizer,
    ):
        super().__init__()
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.image_caption_processor = image_caption_processor
        self.image_caption_model = image_caption_model
        self.llm_model = llm_model
        self.llm_tokenizer = llm_tokenizer
        
        self.model_size = (
            self.get_model_size(self.image_caption_model)
            + self.get_model_size(self.llm_model)
            + 1073741824
        )

    def forward(self, prompt, image_conditioning, max_resulting_tokens):
        if image_conditioning is not None:
            dtype = next(self.image_caption_model.parameters()).dtype
            image_conditioning = [
                (
                    tensor.to(self.device, dtype=dtype),
                    pos,
                    weight
                ) 
                for tensor, pos, weight in image_conditioning
            ]
        
        enhanced_prompt_list = generate_cinematic_prompt(
            self.image_caption_model,
            self.image_caption_processor,
            self.llm_model,
            self.llm_tokenizer,
            prompt,
            image_conditioning,
            max_new_tokens=max_resulting_tokens,
        )
        return enhanced_prompt_list[0]

    @staticmethod
    def get_model_size(model):
        total_size = sum(p.numel() * p.element_size() for p in model.parameters())
        total_size += sum(b.numel() * b.element_size() for b in model.buffers())
        return total_size

    def memory_required(self, input_shape):
        return self.model_size

@comfy_node(name="LTXVPromptEnhancerLoader")
class LTXVPromptEnhancerLoader:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "llm_name": ("STRING", {"default": LLM_NAME[0], "tooltip": "LLM model name."}),
                "image_captioner_name": ("STRING", {"default": IMAGE_CAPTIONER[0], "tooltip": "Image captioning model name."}),
            }
        }

    RETURN_TYPES = ("LTXV_PROMPT_ENHANCER",)
    RETURN_NAMES = ("prompt_enhancer",)
    FUNCTION = "load"
    CATEGORY = "lightricks/LTXV"
    TITLE = "LTXV Prompt Enhancer Loader"
    OUTPUT_NODE = False

    def model_path_download_if_needed(self, model_name):
        model_directory = os.path.join(folder_paths.models_dir, MODELS_PATH_KEY)
        os.makedirs(model_directory, exist_ok=True)
        model_name_ = model_name.rsplit("/", 1)[-1]
        model_path = os.path.join(model_directory, model_name_)

        if not os.path.exists(model_path):
            from huggingface_hub import snapshot_download
            try:
                snapshot_download(repo_id=model_name, local_dir=model_path, local_dir_use_symlinks=False, endpoint="https://hf-mirror.com")
            except Exception:
                shutil.rmtree(model_path, ignore_errors=True)
                raise
        return model_path

    def down_load_llm_model(self, load_device):
        model_path = self.model_path_download_if_needed(LLM_NAME[0])
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            available_memory = torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)
            if available_memory < 4e9:
                comfy.model_management.unload_all_models()

        quantization_config = None
        if Linear4bit is not None and torch.cuda.is_available():
            quantization_config = {"load_in_4bit": True, "bnb_4bit_compute_dtype": torch.float16}

        llm_model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            device_map="auto" if quantization_config else {"": load_device},
            quantization_config=quantization_config,
            mirror="https://hf-mirror.com"
        )
        llm_tokenizer = AutoTokenizer.from_pretrained(model_path, mirror="https://hf-mirror.com")
        return llm_model, llm_tokenizer

    def down_load_image_captioner(self, load_device):
        model_path = self.model_path_download_if_needed(IMAGE_CAPTIONER[0])
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            available_memory = torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)
            if available_memory < 6e9:
                comfy.model_management.unload_all_models()

        image_caption_model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
            torch_dtype=torch.float16,
            device_map={"": load_device},
            mirror="https://hf-mirror.com"
        )
        image_caption_processor = AutoProcessor.from_pretrained(
            model_path,
            trust_remote_code=True,
            mirror="https://hf-mirror.com"
        )
        return image_caption_model, image_caption_processor

    def load(self, llm_name, image_captioner_name):
        load_device = "cuda:0" if torch.cuda.is_available() else "cpu"
        offload_device = comfy.model_management.vae_offload_device()
        
        llm_model, llm_tokenizer = self.down_load_llm_model(load_device)
        image_caption_model, image_caption_processor = self.down_load_image_captioner(load_device)

        enhancer = PromptEnhancer(image_caption_processor, image_caption_model, llm_model, llm_tokenizer)
        patcher = comfy.model_patcher.ModelPatcher(enhancer, load_device, offload_device)
        return (patcher,)

@comfy_node(name="LTXVPromptEnhancer")
class LTXVPromptEnhancer:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "prompt": ("STRING",),
                "prompt_enhancer": ("LTXV_PROMPT_ENHANCER",),
                "max_resulting_tokens": ("INT", {"default": 256, "min": 32, "max": 512}),
            },
            "optional": {
                "image_prompt": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("str",)
    FUNCTION = "enhance"
    CATEGORY = "lightricks/LTXV"
    TITLE = "LTXV Prompt Enhancer"
    OUTPUT_NODE = False

    def enhance(self, prompt, prompt_enhancer: comfy.model_patcher.ModelPatcher, image_prompt: torch.Tensor = None, max_resulting_tokens=256):
        comfy.model_management.free_memory(prompt_enhancer.memory_required([]), comfy.model_management.get_torch_device())
        comfy.model_management.load_model_gpu(prompt_enhancer)
        model = prompt_enhancer.model
        
        image_conditioning = None
        if image_prompt is not None:
            dtype = next(model.image_caption_model.parameters()).dtype
            image_prompt = image_prompt.to(model.device, dtype=dtype)
            print(f"image_prompt shape: {image_prompt.shape}")  # 调试输出
            if image_prompt.dim() == 4 and image_prompt.shape[-1] in [3, 4]:
                image_prompt = image_prompt.permute(0, 3, 1, 2)  # [B, H, W, C] -> [B, C, H, W]
                print(f"image_prompt after permute: {image_prompt.shape}")  # 调试输出
            # 确保张量为 5 维 [B, C, F, H, W]，F=1 表示单帧
            if image_prompt.dim() == 4:
                image_prompt = image_prompt.unsqueeze(2)  # [B, C, H, W] -> [B, C, 1, H, W]
                print(f"image_prompt after unsqueeze: {image_prompt.shape}")  # 调试输出
            image_conditioning = [(image_prompt, 0, 1.0)]
        
        enhanced_prompt = model(prompt, image_conditioning, max_resulting_tokens)
        return (enhanced_prompt,)