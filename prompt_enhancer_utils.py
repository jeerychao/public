import logging
import random
from typing import List, Optional, Tuple, Union

import torch
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

T2V_CINEMATIC_PROMPT = """You are an expert cinematic director with many award winning movies, When writing prompts based on the user input, focus on detailed, chronological descriptions of actions and scenes.
Include specific movements, appearances, camera angles, and environmental details - all in a single flowing paragraph.
Start directly with the action, and keep descriptions literal and precise.
Think like a cinematographer describing a shot list.
Do not change the user input intent, just enhance it.
Keep within 150 words.
For best results, build your prompts using this structure:
Start with main action in a single sentence
Add specific details about movements and gestures
Describe character/object appearances precisely
Include background and environment details
Specify camera angles and movements
Describe lighting and colors
Note any changes or sudden events
Do not exceed the 150 word limit!
Output the enhanced prompt only.

Examples:
user prompt: A man drives a toyota car.
enhanced prompt: A person is driving a car on a two-lane road, holding the steering wheel with both hands. The person's hands are light-skinned and they are wearing a black long-sleeved shirt. The steering wheel has a Toyota logo in the center and black leather around it. The car's dashboard is visible, showing a speedometer, tachometer, and navigation screen. The road ahead is straight and there are trees and fields visible on either side. The camera is positioned inside the car, providing a view from the driver's perspective. The lighting is natural and overcast, with a slightly cool tone.

user prompt: A young woman is sitting on a chair.
enhanced prompt: A young woman with dark, curly hair and pale skin sits on a chair; she wears a dark, intricately patterned dress with a high collar and long, dark gloves that extend past her elbows; the scene is dimly lit, with light streaming in from a large window behind the characters.

user prompt: Aerial view of a city skyline.
enhanced prompt: The camera pans across a cityscape of tall buildings with a circular building in the center. The camera moves from left to right, showing the tops of the buildings and the circular building in the center. The buildings are various shades of gray and white, and the circular building has a green roof. The camera angle is high, looking down at the city. The lighting is bright, with the sun shining from the upper left, casting shadows from the buildings.
"""

I2V_CINEMATIC_PROMPT = """You are an expert cinematic director with many award winning movies, When writing prompts based on the user input, focus on detailed, chronological descriptions of actions and scenes.
Include specific movements, appearances, camera angles, and environmental details - all in a single flowing paragraph.
Start directly with the action, and keep descriptions literal and precise.
Think like a cinematographer describing a shot list.
Keep within 150 words.
For best results, build your prompts using this structure:
Describe the image first and then add the user input. Image description should be in first priority! Align to the image caption if it contradicts the user text input.
Start with main action in a single sentence
Add specific details about movements and gestures
Describe character/object appearances precisely
Include background and environment details
Specify camera angles and movements
Describe lighting and colors
Note any changes or sudden events
Align to the image caption if it contradicts the user text input.
Do not exceed the 150 word limit!
Output the enhanced prompt only.
"""

def tensor_to_pil(tensor):
    print(f"tensor shape in tensor_to_pil: {tensor.shape}")  # 调试输出
    # 确保张量至少有 3 维 (C, H, W)
    if tensor.dim() < 3:
        raise ValueError(f"Tensor must have at least 3 dimensions (C, H, W), got {tensor.shape}")
    
    # 如果张量是 5 维或更高，假设 [B, C, F, H, W] 并取第一帧
    if tensor.dim() >= 5:
        tensor = tensor[:, :, 0, :, :]  # 取第一帧
    if tensor.dim() == 4 and tensor.shape[0] == 1:
        tensor = tensor[0]  # 移除 batch 维度如果 batch_size=1
    
    # 确保张量是 3 维 (C, H, W)
    if tensor.dim() != 3:
        raise ValueError(f"Expected 3D tensor (C, H, W) after processing, got {tensor.shape}")
    
    # 确保值在 [-1, 1] 范围内
    if tensor.min() < -1 or tensor.max() > 1:
        tensor = tensor.clamp(-1, 1)
    
    # Convert from [-1, 1] to [0, 1]
    tensor = (tensor + 1) / 2

    # Rearrange from [C, H, W] to [H, W, C]
    tensor = tensor.permute(1, 2, 0)

    # Convert to numpy array and then to uint8 range [0, 255]
    numpy_image = (tensor.cpu().numpy() * 255).astype(np.uint8)
    print(f"numpy_image shape: {numpy_image.shape}")  # 调试输出

    # 确保通道数正确
    if numpy_image.shape[-1] not in [1, 3, 4]:
        raise ValueError(f"Invalid channel number {numpy_image.shape[-1]}, expected 1, 3, or 4")

    return Image.fromarray(numpy_image)

def generate_cinematic_prompt(
    image_caption_model,
    image_caption_processor,
    prompt_enhancer_model,
    prompt_enhancer_tokenizer,
    prompt: Union[str, List[str]],
    conditioning_items: Optional[List[Tuple[torch.Tensor, int, float]]] = None,
    max_new_tokens: int = 256,
) -> List[str]:
    prompts = [prompt] if isinstance(prompt, str) else prompt

    if conditioning_items is None:
        prompts = _generate_t2v_prompt(
            prompt_enhancer_model,
            prompt_enhancer_tokenizer,
            prompts,
            max_new_tokens,
            T2V_CINEMATIC_PROMPT,
        )
    else:
        dtype = next(image_caption_model.parameters()).dtype
        conditioning_items = [
            (
                tensor.to(prompt_enhancer_model.device, dtype=dtype),
                pos,
                weight
            )
            for tensor, pos, weight in conditioning_items
        ]

        first_frame_conditioning_item = conditioning_items[0]
        first_frames = _get_first_frames_from_conditioning_item(
            first_frame_conditioning_item
        )

        assert len(first_frames) == len(
            prompts
        ), "Number of conditioning frames must match number of prompts"

        prompts = _generate_i2v_prompt(
            image_caption_model,
            image_caption_processor,
            prompt_enhancer_model,
            prompt_enhancer_tokenizer,
            prompts,
            first_frames,
            max_new_tokens,
            I2V_CINEMATIC_PROMPT,
        )

    return prompts

def _get_first_frames_from_conditioning_item(
    conditioning_item: Tuple[torch.Tensor, int, float]
) -> List[Image.Image]:
    frames_tensor = conditioning_item[0]
    print(f"frames_tensor shape: {frames_tensor.shape}")  # 调试输出
    
    # 验证张量维度
    if frames_tensor.dim() != 5:
        raise ValueError(f"Expected frames_tensor with 5 dimensions [B, C, F, H, W], got {frames_tensor.shape}")
    
    batch_size, channels, num_frames, height, width = frames_tensor.shape
    if num_frames < 1:
        raise ValueError("No frames available in conditioning item")
    if height < 1 or width < 1:
        raise ValueError(f"Invalid spatial dimensions: height={height}, width={width}")

    return [
        tensor_to_pil(frames_tensor[i, :, 0, :, :])  # 取第一帧
        for i in range(batch_size)
    ]

def _generate_t2v_prompt(
    prompt_enhancer_model,
    prompt_enhancer_tokenizer,
    prompts: List[str],
    max_new_tokens: int,
    system_prompt: str,
) -> List[str]:
    messages = [
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"user_prompt: {p}"},
        ]
        for p in prompts
    ]

    texts = [
        prompt_enhancer_tokenizer.apply_chat_template(
            m, tokenize=False, add_generation_prompt=True
        )
        for m in messages
    ]
    model_inputs = prompt_enhancer_tokenizer(texts, return_tensors="pt").to(
        prompt_enhancer_model.device
    )

    return _generate_and_decode_prompts(
        prompt_enhancer_model, prompt_enhancer_tokenizer, model_inputs, max_new_tokens
    )

def _generate_i2v_prompt(
    image_caption_model,
    image_caption_processor,
    prompt_enhancer_model,
    prompt_enhancer_tokenizer,
    prompts: List[str],
    first_frames: List[Image.Image],
    max_new_tokens: int,
    system_prompt: str,
) -> List[str]:
    image_captions = _generate_image_captions(
        image_caption_model, image_caption_processor, first_frames
    )

    messages = [
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"user_prompt: {p}\nimage_caption: {c}"},
        ]
        for p, c in zip(prompts, image_captions)
    ]

    texts = [
        prompt_enhancer_tokenizer.apply_chat_template(
            m, tokenize=False, add_generation_prompt=True
        )
        for m in messages
    ]
    model_inputs = prompt_enhancer_tokenizer(texts, return_tensors="pt").to(
        prompt_enhancer_model.device
    )

    return _generate_and_decode_prompts(
        prompt_enhancer_model, prompt_enhancer_tokenizer, model_inputs, max_new_tokens
    )

def _generate_image_captions(
    image_caption_model,
    image_caption_processor,
    images: List[Image.Image],
    system_prompt: str = "<DETAILED_CAPTION>",
) -> List[str]:
    image_caption_prompts = [system_prompt] * len(images)
    inputs = image_caption_processor(
        image_caption_prompts, images, return_tensors="pt"
    ).to(image_caption_model.device)

    dtype = next(image_caption_model.parameters()).dtype
    inputs["pixel_values"] = inputs["pixel_values"].to(dtype=dtype)

    with torch.inference_mode():
        generated_ids = image_caption_model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=1024,
            do_sample=False,
            num_beams=3,
        )

    return image_caption_processor.batch_decode(generated_ids, skip_special_tokens=True)

def _get_random_scene_type():
    """
    Randomly select a scene type to add to the prompt.
    """
    types = [
        "The scene is captured in real-life footage.",
        "The scene is computer-generated imagery.",
        "The scene appears to be from a movie.",
        "The scene appears to be from a TV show.",
        "The scene is captured in a studio.",
    ]
    return random.choice(types)

def _generate_and_decode_prompts(
    prompt_enhancer_model, prompt_enhancer_tokenizer, model_inputs, max_new_tokens: int
) -> List[str]:
    with torch.inference_mode():
        outputs = prompt_enhancer_model.generate(
            **model_inputs, max_new_tokens=max_new_tokens
        )
        generated_ids = [
            output_ids[len(input_ids) :]
            for input_ids, output_ids in zip(model_inputs.input_ids, outputs)
        ]
        decoded_prompts = prompt_enhancer_tokenizer.batch_decode(
            generated_ids, skip_special_tokens=True
        )

    decoded_prompts = [p + f" {_get_random_scene_type()}." for p in decoded_prompts]

    print(decoded_prompts)

    return decoded_prompts