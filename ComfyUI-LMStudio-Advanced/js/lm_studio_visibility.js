import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { ComfyWidgets } from "../../../scripts/widgets.js";

app.registerExtension({
    name: "LMStudio.AdvancedPromptController",
    async setup() {
        api.addEventListener("lmstudio_fetch_preset", async (event) => {
            const node = app.graph.getNodeById(event.detail.node_id);
            if (node) {
                const customPromptWidget = node.widgets?.find(w => w.name === "custom_system_prompt");
                if (customPromptWidget) {
                    customPromptWidget.value = event.detail.prompt || "";
                    node.setDirtyCanvas(true, true);
                }
            }
        });
    },
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // =========================================================================
        // PURE TEXT PREVIEW DISPLAY RENDERER
        // =========================================================================
        if (nodeData.name === "LMStudioTextPreviewNode") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated?.apply(this, arguments);

                // Create a native multiline text preview widget if absent
                let previewWidget = this.widgets?.find(w => w.name === "text_preview");
                if (!previewWidget) {
                    const res = ComfyWidgets["STRING"](
                        this,
                        "text_preview",
                        ["STRING", { multiline: true }],
                        app
                    );
                    previewWidget = res.widget;
                    if (previewWidget.inputEl) {
                        previewWidget.inputEl.readOnly = true;
                        previewWidget.inputEl.style.opacity = "0.85";
                    }
                    previewWidget.serialize = false; // Do not save preview text in graph schema
                }
                return r;
            };

            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                if (onExecuted) onExecuted.apply(this, arguments);
                if (message?.string) {
                    const textValue = Array.isArray(message.string) ? message.string.join("\n") : message.string;
                    const previewWidget = this.widgets?.find(w => w.name === "text_preview");
                    if (previewWidget) {
                        previewWidget.value = textValue;
                        if (previewWidget.inputEl) {
                            previewWidget.inputEl.value = textValue;
                        }
                    }
                    this.onResize?.(this.size);
                    app.graph.setDirtyCanvas(true, true);
                }
            };
        }
    },
    async nodeCreated(node) {
        // =========================================================================
        // PROMPT CONTROLLER CORE VISIBILITY & PRESET HANDLING
        // =========================================================================
        if (node.comfyClass === "LMStudioAdvancedNode" || node.type === "LMStudioAdvancedNode") {
            async function handlePresetChange(presetName) {
                if (presetName === "Default / None") return;
                try {
                    const response = await fetch('/lmstudio/get_preset_prompt', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ preset_name: presetName })
                    });
                    if (response.ok) {
                        const data = await response.json();
                        const customPromptWidget = node.widgets?.find(w => w.name === "custom_system_prompt");
                        if (customPromptWidget && data.prompt) {
                            customPromptWidget.value = data.prompt;
                            app.canvas.setDirty(true, true);
                        }
                    }
                } catch(e) {
                    console.error("[LM Studio UI Node] Preset lookup failed: ", e);
                }
            }

            function updateWidgetVisibility() {
                const modelWidget = node.widgets?.find(w => w.name === "model_name");
                const presetWidget = node.widgets?.find(w => w.name === "system_preset");
                const urlWidget = node.widgets?.find(w => w.name === "fallback_server_url");
                if (!modelWidget || !presetWidget) return;
                if (urlWidget) {
                    if (modelWidget.value !== "No server connected") {
                        urlWidget.type = "HIDDEN";
                    } else {
                        urlWidget.type = "STRING";
                    }
                }
                app.canvas.setDirty(true, true);
            }

            const presetWidget = node.widgets?.find(w => w.name === "system_preset");
            if (presetWidget) {
                const origCallback = presetWidget.callback;
                presetWidget.callback = function (value) {
                    if (origCallback) origCallback.apply(this, arguments);
                    handlePresetChange(value);
                    updateWidgetVisibility();
                };
            }

            const modelWidget = node.widgets?.find(w => w.name === "model_name");
            if (modelWidget) {
                const origCallback = modelWidget.callback;
                modelWidget.callback = function () {
                    if (origCallback) origCallback.apply(this, arguments);
                    updateWidgetVisibility();
                };
            }

            // =========================================================================
            // SAVE / SAVE AS PRESET BUTTON
            // =========================================================================
            const buttonName = "💾 Save / Save As Preset";
            const existingBtn = node.widgets?.find(w => w.name === buttonName);
            if (!existingBtn) {
                const saveBtn = node.addWidget("button", buttonName, null, async () => {
                    const curPresetWidget = node.widgets?.find(w => w.name === "system_preset");
                    const customPromptWidget = node.widgets?.find(w => w.name === "custom_system_prompt");
                    const promptText = customPromptWidget?.value || "";

                    const currentName = (curPresetWidget?.value && curPresetWidget.value !== "Default / None") 
                        ? curPresetWidget.value 
                        : "My_Custom_Preset";

                    const presetName = prompt("Enter preset name to save in LM Studio:", currentName);
                    if (!presetName) return;

                    try {
                        const res = await fetch("/lmstudio/save_preset", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ preset_name: presetName, prompt: promptText })
                        });
                        const result = await res.json();
                        if (result.success) {
                            if (curPresetWidget && curPresetWidget.options?.values) {
                                if (!curPresetWidget.options.values.includes(presetName)) {
                                    curPresetWidget.options.values.push(presetName);
                                }
                                curPresetWidget.value = presetName;
                            }
                            app.canvas.setDirty(true, true);
                            alert(`Preset "${presetName}" saved to LM Studio config!`);
                        } else {
                            alert(`Save failed: ${result.error || "Unknown error"}`);
                        }
                    } catch(err) {
                        alert(`Request failed: ${err}`);
                    }
                });
                saveBtn.serialize = false;
            }

            setTimeout(updateWidgetVisibility, 250);
        }
    }
});