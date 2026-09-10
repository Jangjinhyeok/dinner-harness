# Unity Shader / VFX — specialist reference

Read the project's Editor, render-pipeline, Shader Graph and VFX Graph versions, graphics APIs and
target hardware. Verify version-dependent pass/RenderGraph, shader and VFX APIs against official
docs/source. This is rendering knowledge, not a mandate to adopt a pipeline, tool or separate agent.

## Pipeline and authoring choices

Preserve the existing Built-in/URP/HDRP/custom pipeline unless a change is authorized. URP often
suits a broad platform range; HDRP may suit demanding visual features on supported hardware.
Neither label establishes the project's budget or platform compatibility. Check actual features,
rendering path, XR requirements, package versions and shader support.

Shader Graph supports visual authoring; HLSL can fit reusable libraries, review/debug workflows,
specific APIs or measured control needs even when a graph could express the effect. Subgraphs,
labels, comments and naming prefixes follow project conventions and actual readability/reuse.

Expose intended material controls and reuse common styling/math where it helps. Do not add a shader
framework merely to standardize one effect. Preserve precision, color-space and coordinate-space
contracts, texture formats, pass inputs/outputs and platform compilation requirements.

## Passes, batching and variants

Match shader passes, tags, includes and resource bindings to the selected pipeline and renderer.
URP/HDRP custom-pass and RenderGraph integration vary by version; a ScriptableRenderPass/CustomPass
example is not a universal implementation recipe. Do not mix incompatible pipeline-specific passes
and expect them to work without an intentional integration layer.

SRP Batcher compatibility can reduce CPU state setup for supported shaders. When targeting it,
follow its material-buffer layout requirements, including UnityPerMaterial where required.
Instancing, batching and custom rendering paths have different constraints; lack of SRP Batcher
support alone is not a defect if the chosen path meets requirements.

Keyword sets can multiply variants across passes, stages and graphics APIs, with stripping changing
the built result. Not every keyword simply doubles the final count. Choose shader_feature,
multi_compile and local/global scope according to runtime switching and variant inclusion needs.
Stripping an apparently unused variant can break runtime material/keyword combinations.

Inspect compiled/build variants, loading and runtime coverage before adding stripping callbacks or
budgets. Use the project's build policy rather than a fixed variants-per-shader limit. Preserve
needed variants in player builds; Editor rendering alone is not sufficient verification.

## VFX, post-processing and resources

Choose VFX Graph, Particle System or custom effects by platform support, artist workflow, interaction
and CPU/GPU cost. Particle count alone does not choose the tool. Set capacities/bounds and test
saturation, spawn bursts and culling behavior. Off-screen culling can affect simulation continuity;
do not equate invisible with safe to stop or destroy.

Runtime parameter changes can avoid rebuilding effects, while some state changes need a restart.
Prewarm looping effects when the initial visual state requires it; balance startup cost and residency.
Pooling can reduce measured churn but needs reset, ownership and resource release. Do not mandate
pooling every gameplay effect.

GPU readback can add latency/synchronization; asynchronous readback can be appropriate when results
and platform support justify it. Keep buffers/textures alive until dependent work completes and
release owned resources through the supported render lifecycle. Respect thread/API restrictions.

Volumes can organize post-processing where the pipeline supports them. Bloom, ambient occlusion,
motion blur, LUTs and grading are art/product choices with measurable cost, not essential effects
for every project. Choose precision (half/float), per-vertex/per-pixel work and texture sampling from
numeric/visual requirements and hardware behavior. Lower precision is not automatically faster or safe.

## Profiling and quality

Measure representative scenes on target GPUs using supported Frame Debugger, GPU profiler,
RenderDoc or platform tooling. Separate CPU submission, GPU execution, overdraw, texture bandwidth,
variant compilation and memory costs. Instruction/draw-call counts are investigation signals, not
universal limits or substitutes for frame timing.

Evaluate instancing, batching, atlases, LOD, culling and shader simplification against measured cost
and visual correctness. Quality levels should reflect supported devices/features and project goals;
there is no mandatory Low/Medium/High/Ultra scheme or fixed millisecond allocation per render stage.

Test actual player builds, quality switches, runtime keywords, VFX peaks and minimum supported
hardware. Unavailable GPU/player validation is not_run; source review only identifies candidates.
See [DOTS](unity-dots.md) for Entities Graphics and [UI](unity-ui.md) for UI rendering.
