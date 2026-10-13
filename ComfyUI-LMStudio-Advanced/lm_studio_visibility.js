import { app } from "../../../scripts/app.js";

app.registerExtension({
    name: "LMStudio.AdvancedPromptController",
    async nodeCreated(node) {
        if (node.comfyClass === "LMStudioAdvancedNode") {
            
            function updateWidgetVisibility() {
                // Find our target tracking elements inside the node canvas UI
                const modelWidget = node.widgets.find(w => w.name === "model_name");
                const presetWidget = node.widgets.find(w => w.name === "system_preset");
                const customPromptWidget = node.widgets.find(w => w.name === "custom_system_prompt");
                const urlWidget = node.widgets.find(w => w.name === "fallback_server_url");

                if (!modelWidget || !presetWidget) return;

                // Rule 1: Hide custom system prompt box if a specific preset is actively chosen
                if (customPromptWidget) {
                    if (presetWidget.value !== "Default / None") {
                        customPromptWidget.type = "HIDDEN";
                        if (!customPromptWidget.options) customPromptWidget.options = {};
                        customPromptWidget.options.hideOnZoom = true;
                    } else {
                        customPromptWidget.type = "customtext" || "STRING";
                        delete customPromptWidget.options.hideOnZoom;
                    }
                }

                // Rule 2: Only show fallback server URL option if no main local server connection is active
                if (urlWidget) {
                    if (modelWidget.value !== "No server connected") {
                        urlWidget.type = "HIDDEN";
                        if (!urlWidget.options) urlWidget.options = {};
                        urlWidget.options.hideOnZoom = true;
                    } else {
                        urlWidget.type = "STRING";
                        delete urlWidget.options.hideOnZoom;
                    }
                }
                
                // Force ComfyUI canvas redraw to apply styling transitions instantly
                node.setSize(node.computeSize());
                app.canvas.setDirty(true, true);
            }

            // Bind triggers directly to dropdown changes
            const presetWidget = node.widgets.find(w => w.name === "system_preset");
            if (presetWidget) {
                const origCallback = presetWidget.callback;
                presetWidget.callback = function () {
                    if (origCallback) origCallback.apply(this, arguments);
                    updateWidgetVisibility();
                };
            }

            const modelWidget = node.widgets.find(w => w.name === "model_name");
            if (modelWidget) {
                const origCallback = modelWidget.callback;
                modelWidget.callback = function () {
                    if (origCallback) origCallback.apply(this, arguments);
                    updateWidgetVisibility();
                };
            }

            // Run an immediate evaluation loop during node instantiation
            setTimeout(updateWidgetVisibility, 100);
        }
    }
});
