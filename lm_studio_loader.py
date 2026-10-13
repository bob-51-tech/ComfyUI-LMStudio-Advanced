import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import comfy.utils

def query_lmstudio_models(base_url):
    """Attempt to get models from either v1 or v0 endpoint."""
    models = []
    # Try v1 first
    try:
        with urllib.request.urlopen(f"{base_url}/api/v1/models", timeout=1.5) as resp:
            data = json.loads(resp.read().decode())
            for m in data.get('models', []):
                if 'key' in m:
                    models.append(m['key'])
                elif 'id' in m:
                    models.append(m['id'])
    except Exception:
        pass

    if not models:
        # Fallback to v0
        try:
            with urllib.request.urlopen(f"{base_url}/api/v0/models", timeout=1.5) as resp:
                data = json.loads(resp.read().decode())
                models = [model['id'] for model in data.get('data', [])]
        except Exception:
            pass

    return models


class LMStudioAdvancedNode:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        current_url = "http://localhost:1234"
        models = query_lmstudio_models(current_url)
        if not models:
            models = ["No server connected"]

        presets = ["Default / None"]
        preset_paths = [
            os.path.expandvars(r'%USERPROFILE%\.lmstudio\config-presets'), 
            os.path.expanduser('~/.lmstudio/config-presets'),             
            os.path.expandvars(r'%APPDATA%\lmstudio\config-presets')      
        ]
        
        for path in preset_paths:
            if os.path.exists(path):
                try:
                    files = os.listdir(path)
                    presets.extend([f.replace('.json', '') for f in files if f.endswith('.json')])
                    break
                except Exception:
                    pass

        return {
            "required": {
                "model_name": (models, {}),
                "system_preset": (presets, {}),
                "custom_system_prompt": ("STRING", {"multiline": True, "default": ""}),
                "user_prompt": ("STRING", {"multiline": True, "default": ""}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.05}),
                "top_p": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.05}),
                "context_length": ("INT", {"default": 4096, "min": 512, "max": 32768, "step": 512}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "thinking_mode": (["Disable Completely", "Extract & Include", "Hide From Output"], {"default": "Disable Completely"}),
                "unload_model_after_generation": (["True", "False"], {"default": "True"}),
            },
            "optional": {
                "fallback_server_url": ("STRING", {"default": "http://localhost:1234"}),
                "kv_cache_quant": (["none", "q8_0", "q4_0"], {"default": "none"}),
                "hf_download_repo": ("STRING", {"default": "lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text_output",)
    FUNCTION = "generate_text"
    CATEGORY = "LLM/LM-Studio"

    def _unload_model(self, base_url, model_name):
        """Discovers running instances and reliably executes unload commands."""
        instances_to_unload = set()

        # 1. Discover active instance_id from GET /api/v1/models
        try:
            req = urllib.request.Request(f"{base_url}/api/v1/models")
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode())
                for item in data.get("models", []):
                    item_key = item.get("key", "")
                    if model_name in item_key or item_key in model_name:
                        for inst in item.get("loaded_instances", []):
                            if inst.get("id"):
                                instances_to_unload.add(inst["id"])
        except Exception:
            pass

        # 2. Check /api/v0/models if v1 had no matches
        if not instances_to_unload:
            try:
                req = urllib.request.Request(f"{base_url}/api/v0/models")
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    data = json.loads(resp.read().decode())
                    for item in data.get("data", []):
                        if (model_name in item.get("id", "")) and item.get("state") == "loaded":
                            instances_to_unload.add(item["id"])
            except Exception:
                pass

        # 3. If discovery failed to find instances, target model_name directly
        if not instances_to_unload:
            instances_to_unload.add(model_name)

        # 4. Issue unload calls without invalid extra keys
        for target_id in instances_to_unload:
            unloaded = False
            # Try v1 unload endpoint
            try:
                payload = json.dumps({"instance_id": target_id}).encode('utf-8')
                req = urllib.request.Request(
                    f"{base_url}/api/v1/models/unload",
                    data=payload,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp.read()
                    print(f"[LM Studio Node] Successfully unloaded '{target_id}' via /api/v1/models/unload.")
                    unloaded = True
            except urllib.error.HTTPError as e:
                # Fallback to v0 if v1 endpoint not found (404)
                if e.code == 404:
                    try:
                        payload = json.dumps({"instance_id": target_id}).encode('utf-8')
                        req = urllib.request.Request(
                            f"{base_url}/api/v0/models/unload",
                            data=payload,
                            headers={'Content-Type': 'application/json'},
                            method='POST'
                        )
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            resp.read()
                            print(f"[LM Studio Node] Successfully unloaded '{target_id}' via /api/v0/models/unload.")
                            unloaded = True
                    except Exception as e_v0:
                        print(f"[LM Studio Node] Failed v0 unload for '{target_id}': {e_v0}")
                else:
                    print(f"[LM Studio Node] Unload returned HTTP {e.code}: {e.reason}")
            except Exception as e:
                print(f"[LM Studio Node] Auto-unload warning for '{target_id}': {str(e)}")

    def generate_text(self, model_name, system_preset, custom_system_prompt, user_prompt, 
                      temperature, top_p, context_length, seed, thinking_mode, 
                      unload_model_after_generation, fallback_server_url="http://localhost:1234", 
                      kv_cache_quant="none", hf_download_repo=""):
        
        base_url = (fallback_server_url.strip() if model_name == "No server connected" else "http://localhost:1234").rstrip("/")

        pbar = comfy.utils.ProgressBar(100)
        pbar.update(10)
        start_time = time.time()

        if model_name == "No server connected" or not model_name:
            if hf_download_repo:
                try:
                    req_data = json.dumps({"modelRepoId": hf_download_repo}).encode('utf-8')
                    req = urllib.request.Request(f"{base_url}/api/v1/models/download", data=req_data, headers={'Content-Type': 'application/json'})
                    with urllib.request.urlopen(req) as resp:
                        return (f"Triggered download for {hf_download_repo}. Check LM Studio.",)
                except Exception as e:
                    return (f"Download call failed: {str(e)}",)
            return (f"Error: No server found at {base_url}",)

        pbar.update(40)
        final_system_prompt = custom_system_prompt

        messages = []
        if final_system_prompt.strip():
            messages.append({"role": "system", "content": final_system_prompt.strip()})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": -1, 
            "seed": seed,
            "config": {
                "contextLength": context_length
            }
        }
        
        if thinking_mode == "Disable Completely":
            payload["reasoning_effort"] = "none"
            payload["config"]["thinking"] = {"type": "disabled"}
        
        if kv_cache_quant != "none":
            payload["config"]["kvCacheQuantizationType"] = kv_cache_quant

        pbar.update(60)
        output_text = ""
        try:
            req_data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(f"{base_url}/v1/chat/completions", data=req_data, headers={'Content-Type': 'application/json'})
            
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode())
                
                choice = res_data['choices'][0]
                base_content = choice['message'].get('content', '')
                thinking_content = choice['message'].get('reasoning_content', '') or choice['message'].get('reasoning', '')
                
                if thinking_mode == "Extract & Include" and thinking_content:
                    output_text = f"<thinking>\n{thinking_content}\n</thinking>\n\n{base_content}"
                else:
                    output_text = base_content
                
                usage = res_data.get('usage', {})
                elapsed = time.time() - start_time
                print("\n" + "="*40 + "\n[LM STUDIO NODE INFERENCE STATS]\n" + "="*40)
                print(f"• Execution Time: {elapsed:.2f} seconds")
                print(f"• Prompt Tokens:  {usage.get('prompt_tokens', 'N/A')}")
                print(f"• Reply Tokens:   {usage.get('completion_tokens', 'N/A')}")
                print(f"• Total Window:   {usage.get('total_tokens', 'N/A')}")
                print("="*40 + "\n")
                
        except Exception as e:
            output_text = f"Inference execution failed via LM Studio API wrapper ({base_url}): {str(e)}"

        pbar.update(90)
        
        if unload_model_after_generation == "True":
            print(f"[LM Studio Node] Finished inference. Requesting VRAM unload for: {model_name}")
            self._unload_model(base_url, model_name)

        pbar.update(100)
        return (output_text,)

    @classmethod
    def IS_CHANGED(s, **kwargs):
        return float("nan")


class LMStudioTextPreviewNode:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
            }
        }

    INPUT_IS_LIST = False
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "preview_text"
    OUTPUT_NODE = True
    CATEGORY = "LLM/LM-Studio"
    
    def preview_text(self, text):
        return {"ui": {"string": [text]}, "result": (text,)}
        
class LMStudioTaskPrefixNode:
    TAG_MAP = {
        "none": "",
        "text to image": "t2i:",
        "image to image": "i2i:",
        "text to video": "t2v:",
        "image/ref to video": "i2v:",
    }

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "task": (["none", "text to image", "image to image", "text to video", "image/ref to video"], {"default": "none"}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("tagged_prompt",)
    FUNCTION = "apply_tag"
    CATEGORY = "LLM/LM-Studio"

    def apply_tag(self, task, prompt):
        tag = self.TAG_MAP.get(task, "t2i:")
        cleaned_prompt = prompt.strip()

        # Strip any existing task tag if the user toggled tasks to avoid duplicate tags like "t2v: t2i: ..."
        for known_tag in self.TAG_MAP.values():
            if cleaned_prompt.startswith(known_tag):
                cleaned_prompt = cleaned_prompt[len(known_tag):].strip()
                break

        return (f"{tag} {cleaned_prompt}",)