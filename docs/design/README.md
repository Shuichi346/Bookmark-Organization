# Interface specification

Reference: concept.png, generated with built-in Image Gen. This is a state inventory, not production UI or real results. The implementation follows the plan rather than incidental generated copy: use the two specified models, a single Automatic/English/日本語 selector, one combined selected region, and an explicit destination. No estimate of remaining time without evidence. Generated names remain Japanese irrespective of interface language.

Pure white background (#ffffff), sidebar #f5f7f9, text #182433, muted #637083, border #dce2e8, accent #087f75, error #a52c39. System sans-serif including Japanese fallbacks. Heading 28px/1.3, body and controls 14px/1.5, tables 13px/1.5. Spacing 8/16/24px; radius 6px. No image overlays, decorative imagery or gradients. No icon library: semantic native form controls and text suffice.

Header: brand, Settings, language selector. Main: Import HTML empty state; imported original tree with checkboxes, all selector, count and explicit destination; analyze action. Job state: stage counts, progress, status table, Pause/Resume/Cancel/Retry failed, Create proposal and explicit permit-incomplete choice. Cancel is enabled for running/paused jobs. Cancelled jobs show a terminal status and guidance to start a new analysis; job controls are disabled and proposal creation is unavailable. Original bookmarks and saved results remain intact. Proposal state: original/suggested names, original/new folder, retrieval and analysis status, summaries/tags, search/status filter, 25-row pagination, editable names/placement, integrity result, Export HTML and original download. Settings: independent provider/base/model selectors, model discovery, timeout/size/rendering/context/clustering settings.

Japanese and English copy lives in the matching JSON catalogs. Language switch preserves scope in session storage; jobs/proposals live in SQLite. Empty, validation, retrieval and model failures show catalog messages with actionable retry controls. No executable imported HTML enters the UI.

Desktop (1440×900): header 72px, sidebar 280px, main flexible; local scroll for dense tables. Mobile (390×844): header wraps, sidebar stacks, controls fill available width, table scroll remains contained. Primary controls remain keyboard focusable with visible focus. Motion: only native progress, no animation required.

Automated verification asserts document language, catalog/client consistency, palette/type tokens, viewport overflow, focusable controls and workflow. Per PLANS.md, no AI-driven browser interaction or screenshot fidelity grading is performed.

## Image Gen prompt

Built-in tool, ui-mockup, saved as concept.png:

> Create a legible professional app design reference board with three coordinated full screens and a mobile state for a local Bookmark Organization tool. Use pure white background, pale gray sidebar, navy text #182433, teal #087f75 primary controls, fine gray borders, system sans serif. No decorative hero, imagery, fake metrics or badges. Dense but airy table-driven practical utility, code-native controls in implementation. Main screen header Bookmark Organization, Settings and selector Automatic / English / 日本語. Left rail original folder tree with checkboxes, import HTML button. Main heading Organize your bookmarks. Selection summary and destination dropdown, primary Analyze selected. State 2 processing with progress bar, per-url status table and Pause/Resume controls. State 3 before/after comparison table Original name / Suggested name / Location / Status, search and pagination, editable names and folder choices, integrity count and Export HTML. Settings panel runtime LM Studio / Ollama, separate model selectors for content and embeddings, local endpoint inputs, Test connection. Mobile 390px layout stacks tree and workflow and horizontally scrolls tables. Empty/error states show import-first and retry causes. Include Japanese main heading ブックマークを整理 and button 選択範囲を分析 in a Japanese state. Synthetic example rows FastAPI docs and TypeScript handbook clearly show data examples. Show all required states as readable individually framed compact app panels. Flat UI reference only no illustration no invented navigation. Typography heading 28px, controls/body14px, data table13px, spacing8/16/24px, radii6px.

## Inference settings amendment

The settings screen now includes Runtime/App source selection. App is the default, with thinking off. Runtime disables the app controls without changing their current values. App mode enables thinking and temperature, plus Top K, Top P, Min P, repetition penalty and presence penalty toggles/values. Controls use the existing two-column form grid, collapsing on narrow screens. Model response wait explains that 0 means unlimited. This is a user-requested extension beyond the original generated reference; no additional image fidelity claim is made.


## OpenRouter provider amendment

Both role selectors include OpenRouter alongside LM Studio and Ollama. Selecting it fixes the endpoint to `https://openrouter.ai/api/v1`, clears the previous provider's model choice and reveals a shared password-only API-key field with localized input-transmission/usage information. After a provider change, either discover candidates or type the exact model ID. Save clears the typed key; reload displays only configured status. Blank entries preserve the configured key. Local model selectors retain loopback restrictions and never receive the cloud credential. Generation catalogs include text models advertising structured outputs; embedding catalogs include text-to-embedding models. Model-supported sampling and reasoning controls use OpenRouter's parameter names.


## Editable model fields

Generation and embedding model fields each pair a native text input with a labeled suggestion select. Users can type exact IDs or pick suggestions, which the app filters as they type. Discovery replaces only the candidate lists, preserving current input even when it is absent from the returned catalog. Provider changes clear the corresponding field and stale candidates; saving trims surrounding whitespace. Model availability and role validation at processing time remain unchanged.
