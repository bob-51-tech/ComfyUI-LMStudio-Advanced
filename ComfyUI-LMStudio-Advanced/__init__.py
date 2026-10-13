from .lm_studio_loader import LMStudioAdvancedNode, LMStudioTextPreviewNode, LMStudioTaskPrefixNode
import os
import json
from server import PromptServer
from aiohttp import web

NODE_CLASS_MAPPINGS = {
    "LMStudioAdvancedNode": LMStudioAdvancedNode,
    "LMStudioTextPreviewNode": LMStudioTextPreviewNode,
    "LMStudioTaskPrefixNode": LMStudioTaskPrefixNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LMStudioAdvancedNode": "LM Studio Advanced Prompt Controller",
    "LMStudioTextPreviewNode": "LM Studio Pure Text Preview",
    "LMStudioTaskPrefixNode": "LM Studio Task Prefix / Tag"
}

WEB_DIRECTORY = "./js"

@PromptServer.instance.routes.post("/lmstudio/get_preset_prompt")
async def get_preset_prompt(request):
    try:
        json_data = await request.json()
        preset_name = json_data.get("preset_name")
        
        preset_paths = [
            os.path.expandvars(r'%USERPROFILE%\.lmstudio\config-presets'),
            os.path.expanduser('~/.lmstudio/config-presets'),
            os.path.expandvars(r'%APPDATA%\lmstudio\config-presets')
        ]
        
        for path in preset_paths:
            preset_file = os.path.join(path, f"{preset_name}.json")
            if os.path.exists(preset_file):
                with open(preset_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    fields = data.get("operation", {}).get("fields", [])
                    for field in fields:
                        if field.get("key") == "llm.prediction.systemPrompt":
                            return web.json_response({"prompt": field.get("value", "")})
                            
                    if "systemPrompt" in data:
                        return web.json_response({"prompt": data["systemPrompt"]})
                        
        return web.json_response({"prompt": ""})
    except Exception as e:
        return web.json_response({"error": str(e), "prompt": ""}, status=500)

@PromptServer.instance.routes.post("/lmstudio/save_preset")
async def save_preset_prompt(request):
    try:
        json_data = await request.json()
        preset_name = json_data.get("preset_name", "").strip()
        prompt_text = json_data.get("prompt", "")

        if not preset_name or preset_name == "Default / None":
            return web.json_response({"error": "Invalid preset name"}, status=400)

        # Detect the first writable LM Studio directory
        target_dir = None
        preset_paths = [
            os.path.expandvars(r'%USERPROFILE%\.lmstudio\config-presets'),
            os.path.expanduser('~/.lmstudio/config-presets'),
            os.path.expandvars(r'%APPDATA%\lmstudio\config-presets')
        ]
        for p in preset_paths:
            if os.path.exists(p):
                target_dir = p
                break

        if not target_dir:
            # Fallback create default path
            target_dir = preset_paths[0]
            os.makedirs(target_dir, exist_ok=True)

        file_path = os.path.join(target_dir, f"{preset_name}.json")

        # Read existing file structure if editing, or create a standard schema
        data = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data["name"] = preset_name
        data["systemPrompt"] = prompt_text
        if "operation" not in data:
            data["operation"] = {"fields": []}

        # Keep LM Studio field structure intact
        fields = data["operation"].get("fields", [])
        field_found = False
        for field in fields:
            if field.get("key") == "llm.prediction.systemPrompt":
                field["value"] = prompt_text
                field_found = True
                break
        if not field_found:
            fields.append({"key": "llm.prediction.systemPrompt", "value": prompt_text})
        data["operation"]["fields"] = fields

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return web.json_response({"success": True, "preset_name": preset_name})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
