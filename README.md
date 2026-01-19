# README.md

## THREE-BODY MILITARY HIERARCHY DESKTOP AUTOMATION AGENT

### Technical Architecture Documentation

---

## 1. SYSTEM ARCHITECTURE

### Three-Body Hierarchy Model

The system implements a strict three-tier command structure inspired by military operations, where each persona operates at a distinct abstraction level with non-overlapping responsibilities:

**STRATEGIST (General - Strategic Command)**
- **Invocation**: Once at mission initialization
- **Input**: User mission description + initial screenshot (vision-augmented)
- **Output**: 6-section strategic doctrine containing:
  1. Mission restatement (operational terms)
  2. Reconnaissance phase definition
  3. 4-7 intermediate phase options (branching execution paths)
  4. Verification phase criteria
  5. Operational risks (context-specific hazards)
  6. Field commander directives (high-level guidance for Tactician)
- **Role**: Establishes immutable strategic framework; never invoked again during mission
- **Temperature**: 0.3 (deterministic planning)
- **Token Budget**: 1200 max tokens

**TACTICIAN (Field Commander - Phase Management)**
- **Invocation**: Turn 1 and every `TACTICIAN_INTERVAL` turns (default: 5)
- **Input**: Strategic doctrine + screenshot + action history + current phase state
- **Output**: Tool calls (`spawn_executor_prompt`, `update_phase_tools`) OR text status
- **Role**: 
  - Analyzes visual evidence for phase completion/transition triggers
  - Spawns phase-specific executor configurations via tool-based prompt generation
  - Manages tool subsetting (which tools available per phase)
  - Monitors execution progress without micromanaging individual actions
- **Tools Available**: 2 meta-tools (not action tools)
  - `spawn_executor_prompt`: Creates/updates executor system prompt (200-400 words)
  - `update_phase_tools`: Specifies tool name whitelist for executor
- **Temperature**: 0.4 (balanced adaptation)
- **Token Budget**: 800 max tokens

**EXECUTOR (Operative - Single Action Execution)**
- **Invocation**: Every turn (after tactician initializes configuration)
- **Input**: Current executor prompt + screenshot + history + available tools (phase-filtered)
- **Output**: Single tool call with detailed justification (50+ words)
- **Role**:
  - Executes ONE precise action per turn based on phase goals
  - Provides visual evidence + reasoning + prediction for each action
  - No strategic thinking—operates within tactician-defined constraints
- **Tools Available**: Subset of 9 action tools (filtered by tactician)
- **Temperature**: 0.5 (1.5× multiplier if loop detected)
- **Token Budget**: 1024 max tokens

### Control Flow

**Turn-Based Execution Loop:**

```
Initialization:
├─ Capture screenshot (512×256)
├─ Invoke STRATEGIST → doctrine
├─ Build tactician_prompt (doctrine-injected)
└─ Initialize AgentState

Main Loop (per turn):
├─ 1. Increment turn counter
├─ 2. Capture fresh screenshot + save to dumps/
├─ 3. Update state.screenshot
│
├─ 4. TACTICIAN CHECK (turn==1 OR turn % 5 == 0):
│   ├─ Invoke tactician with oversight prompt
│   ├─ Parse tool calls:
│   │   ├─ spawn_executor_prompt → extract prompt + phase
│   │   └─ update_phase_tools → extract tool_names[]
│   ├─ If tools present: update_executor_context()
│   ├─ If turn==1 AND no tools: FALLBACK to default config
│   └─ Sleep TIMING_TURN_DELAY (3.5s)
│
├─ 5. EXECUTOR ACTION (if prompt configured):
│   ├─ Invoke executor with phase-filtered tools
│   ├─ Parse single tool_call (tool_calls[0] only)
│   ├─ If report_completion → mission complete
│   ├─ Execute tool action (Windows API calls)
│   ├─ Record to history (add_history)
│   └─ Prune history to MAX_HISTORY_ITEMS (10)
│
└─ 6. Sleep TIMING_TURN_DELAY (3.5s) and repeat
```

**Oversight Intervals:**
- **Turn 1**: Mandatory tactician oversight (establishes initial phase)
- **Every 5 turns**: Tactician reassesses phase status
- **Between oversight**: Executor operates autonomously with current configuration

### Persona Lifecycle

**Dynamic Prompt Spawning Mechanism:**

1. **Tactician decides phase transition** based on visual evidence
2. **Calls `spawn_executor_prompt` tool** with:
   - `prompt`: Complete system prompt for executor (200-400 words)
   - `phase`: Phase identifier (e.g., "RECONNAISSANCE", "EXECUTION_NOTEPAD")
   - `rationale`: Justification for prompt update (50-100 words)
3. **Calls `update_phase_tools` tool** with:
   - `tool_names`: Array of tool names (NOT full JSON schemas)
   - `rationale`: Why these tools for this phase
4. **State update**: `state.update_executor_context(prompt, phase, tool_names)`
5. **Tool filtering**: `state.get_executor_tools()` returns phase-appropriate subset from `TOOL_REGISTRY`

**Critical Design**: Executor prompts are NOT hardcoded—they are generated dynamically by the tactician based on strategic doctrine and current mission context. This enables context-specific risk warnings and precision requirements.

### Tool-Based Configuration

**Tool Subsetting Architecture:**

```python
TOOL_REGISTRY = {tool["function"]["name"]: tool for tool in EXECUTOR_TOOLS}
# Maps tool names → full OpenAI function definitions

state.current_tool_names = ["click_element", "press_key", "report_completion"]
# Tactician specifies names only (not 500+ line JSON schemas)

filtered_tools = state.get_executor_tools()
# Returns [TOOL_REGISTRY[name] for name in current_tool_names]
```

**Phase-Specific Tool Examples:**
- **Reconnaissance**: `["click_element", "scroll_down", "scroll_up"]` (no completion)
- **Execution**: `["click_element", "type_text", "press_key", "drag_element"]`
- **Verification**: `["click_element", "report_completion"]` (completion enabled)

**Token Efficiency**: Sending only relevant tools per phase reduces API payload by 60-80% compared to always sending all 9 tools.

### State Management

**Client-Side State (`AgentState` class):**

```python
class AgentState:
    # Mission context
    task: str                          # User mission description
    screenshot: bytes                  # Current PNG screenshot
    screen_dims: Tuple[int, int]       # Physical screen size (sw, sh)
    turn: int                          # Current turn number
    
    # Three-body hierarchy state
    strategist_doctrine: str           # Immutable strategic plan
    tactician_prompt: str              # Doctrine-injected tactician prompt
    current_executor_prompt: str       # Phase-specific executor prompt
    current_phase: str                 # Phase identifier
    current_tool_names: List[str]      # Tool name whitelist
    
    # History
    history: List[Dict]                # Last 10 actions (pruned)
    full_archive: List[Dict]           # Complete history (if enabled)
```

**Stateless API Contract:**
- **No server-side conversation history**: Each API call is independent
- **All context resent every turn**: Screenshot + history + doctrine transmitted in full
- **State reconstruction**: History text rebuilt via `build_history_text()` each turn
- **Assumption**: LM Studio `/v1/chat/completions` endpoint is stateless OpenAI-compatible

**History Management:**
- **Recent history**: Last 8 actions sent to LLM (compact format)
- **In-memory storage**: Last 10 actions retained in `state.history`
- **Simple truncation**: `prune_history()` removes oldest entries (no priority tiers)
- **Full archive**: Optional complete history dump to JSON checkpoint

---

## 2. COMPONENT INVENTORY

### Persona System

**`STRATEGIST_PROMPT`** (419 words):
- **Input Contract**: Mission description + initial screenshot (vision)
- **Output Contract**: Exactly 6 sections (mission restatement, recon phase, 4-7 intermediate options, verification, risks, directives)
- **Key Requirement**: "OPERATIONAL RISKS" section must include context-specific UI hazards (e.g., "Small brush in Paint → drawings invisible")
- **Field Commander Directives**: 150-word guidance on phase transitions, tool selection, risk mitigation
- **Design Constraint**: "Be concise. No conversational filler." (targets 2B model limitations)

**`TACTICIAN_PROMPT_TEMPLATE`** (formatted with `{mission}` and `{doctrine}`):
- **Role Definition**: "Field Commander managing phase transitions"
- **Decision Framework**: Three-phase model (Reconnaissance → Execution → Verification)
- **Tool Usage Instructions**:
  - `spawn_executor_prompt`: When phase transitions occur based on visual evidence
  - `update_phase_tools`: Match toolset to phase needs
- **Critical Directive**: "Only spawn new executor when phase actually changes based on visual evidence" (prevents unnecessary reconfigurations)
- **Completion Tool Rule**: "Include report_completion ONLY in verification phase"

**`EXECUTOR_FALLBACK_PROMPT`** (123 words):
- **Trigger**: Used when tactician fails to provide configuration on turn 1
- **Capabilities**: Generic action executor with coordinate system reminder
- **Limitations**: No phase-specific risk warnings or precision requirements
- **Coordinate Format**: "[x,y] format only, 0-1000 normalized scale"
- **Justification Requirement**: "Detailed 50+ word justification" per action

**Dynamic Executor Prompts** (spawned by tactician):
- **Not stored in code**: Generated per phase by `spawn_executor_prompt` tool
- **Content Requirements** (per tool definition):
  - Phase goals (what to accomplish)
  - Precision requirements (coordinate accuracy, timing)
  - Risk warnings (phase-specific hazards from strategist)
  - Coordinate system reminder (0-1000 scale)
  - Justification requirements (50+ words)
- **Length**: 200-400 words (enforced by tool parameter description)

### Tool Definitions

**`TACTICIAN_TOOLS`** (2 meta-tools):

1. **`spawn_executor_prompt`**:
   ```json
   {
     "name": "spawn_executor_prompt",
     "parameters": {
       "prompt": "Complete system prompt for Executor (200-400 words)",
       "phase": "Phase name (e.g., 'RECONNAISSANCE')",
       "rationale": "Why this prompt update is needed (50-100 words)"
     }
   }
   ```
   - **Purpose**: Create phase-specific executor configuration
   - **Validation**: LLM enforces JSON schema (no manual parsing)
   - **Not available to executor**: Prevents self-modification

2. **`update_phase_tools`**:
   ```json
   {
     "name": "update_phase_tools",
     "parameters": {
       "tool_names": ["click_element", "press_key", "report_completion"],
       "rationale": "Why these specific tools (50 words)"
     }
   }
   ```
   - **Purpose**: Specify tool name whitelist for executor
   - **Design**: Tool names only (not 500-line definitions)
   - **Registry Lookup**: `TOOL_REGISTRY` maps names to full schemas

**`EXECUTOR_TOOLS`** (9 action tools):

1. **`report_completion`**: Task completion with visual evidence (100 words)
2. **`click_element`**: Single click with justification + label + position [x,y]
3. **`double_click_element`**: Double-click (same parameters)
4. **`right_click_element`**: Context menu trigger
5. **`drag_element`**: Drag from start [x,y] to end [x,y]
6. **`type_text`**: Unicode text input (no length limit in schema)
7. **`press_key`**: Keyboard shortcuts (e.g., "ctrl+c", "windows")
8. **`scroll_down`**: Scroll downward (delta=-120)
9. **`scroll_up`**: Scroll upward (delta=+120)

**All action tools require `justification` parameter**: 30-50 words describing visual evidence, reasoning, expected outcome.

**`TOOL_REGISTRY`**:
```python
TOOL_REGISTRY = {tool["function"]["name"]: tool for tool in EXECUTOR_TOOLS}
# Enables O(1) lookup for tool subsetting
```

### State Classes

**`AgentState`** (detailed field breakdown):

**Initialization Parameters**:
- `task: str` - User mission description (immutable)
- `initial_screenshot: bytes` - PNG from `capture_png()` at startup
- `screen_dims: Tuple[int, int]` - (sw, sh) from `get_screen_size()`

**Hierarchy State Fields**:
- `strategist_doctrine: str` - Output from `invoke_strategist()` (set once)
- `tactician_prompt: str` - `TACTICIAN_PROMPT_TEMPLATE` formatted with doctrine
- `current_executor_prompt: Optional[str]` - From `spawn_executor_prompt` tool call
- `current_phase: str` - Phase identifier (default: "INIT")
- `current_tool_names: List[str]` - From `update_phase_tools` tool call

**Execution State Fields**:
- `turn: int` - Current turn number (incremented per loop iteration)
- `screenshot: bytes` - Latest PNG (updated every turn)
- `history: List[Dict]` - Last 10 actions (pruned)
- `full_archive: List[Dict]` - Complete history (optional, if `ENABLE_FULL_ARCHIVE=True`)

**Key Methods**:

1. **`update_executor_context(prompt, phase, tool_names)`**:
   - Sets `current_executor_prompt`, `current_phase`, `current_tool_names`
   - Called when tactician provides configuration updates
   - No validation—assumes tactician output is valid

2. **`get_executor_tools() -> List[Dict]`**:
   - Filters `TOOL_REGISTRY` to include only `current_tool_names`
   - Returns empty list if `current_tool_names` is empty
   - Silently skips unknown tool names (no error raised)

3. **`add_history(tool, args, justification, result, screenshot_path)`**:
   - Appends entry with turn number, tool name, arguments, outcome
   - Also appends to `full_archive` if enabled
   - Does NOT enforce length limits (pruning done separately)

### Invocation Functions

**`invoke_strategist(task: str, screenshot: bytes) -> str`**:
- **Endpoint**: `POST /v1/chat/completions`
- **Messages**:
  - System: `STRATEGIST_PROMPT`
  - User: Text (mission) + image_url (base64 PNG)
- **Parameters**: `temperature=0.3`, `max_tokens=1200`, no tools
- **Return**: Doctrine text (6 sections) or error string
- **Error Handling**: Returns `f"Strategist invocation failed: {e}"` (no exception raised)

**`invoke_tactician(state: AgentState) -> Tuple[Optional[str], Optional[str], Optional[List[str]]]`**:
- **Endpoint**: `POST /v1/chat/completions`
- **Messages**:
  - System: `state.tactician_prompt` (doctrine-injected)
  - User: History text + screenshot
- **Parameters**: `temperature=0.4`, `max_tokens=800`, `tools=TACTICIAN_TOOLS`, `tool_choice="auto"`
- **Return**: `(executor_prompt, phase_name, tool_names)` if tools called, else `(None, None, None)`
- **Tool Call Parsing**:
  - Iterates `tool_calls` array
  - Extracts `spawn_executor_prompt` → prompt, phase, rationale
  - Extracts `update_phase_tools` → tool_names, rationale
  - Prints rationales to console (logging)
- **No Tool Calls**: Prints status text, returns `(None, None, None)`
- **Error Handling**: Returns `(None, None, None)` on exception (logs to console)

**`invoke_executor(state: AgentState) -> Optional[Dict]`**:
- **Endpoint**: `POST /v1/chat/completions`
- **Messages**:
  - System: `state.current_executor_prompt` (dynamically spawned)
  - User: History text + screenshot
- **Parameters**: 
  - `temperature=0.5` (or 0.75 if loop detected)
  - `max_tokens=1024`
  - `tools=state.get_executor_tools()` (phase-filtered)
  - `tool_choice="auto"`
- **Return**: Single tool call dict (`tool_calls[0]`) or `None`
- **Single-Action Enforcement**: Only first tool call processed (no iteration over array)
- **Loop Detection**: Calls `detect_terminal_loop()` → adjusts temperature
- **Error Handling**: Returns `None` on exception or missing tool calls

---

## 3. DATA FLOW ANALYSIS

### Startup Sequence

```
1. main() entry
   ├─ init_dpi() → Set PER_MONITOR_AWARE_V2
   ├─ Input: task = user mission string
   └─ capture_png(512, 256) → (png, sw, sh)

2. PHASE 0: STRATEGIC COMMAND
   ├─ invoke_strategist(task, png)
   │   ├─ POST /v1/chat/completions
   │   │   ├─ messages: [system=STRATEGIST_PROMPT, user={text+image}]
   │   │   └─ temperature=0.3, max_tokens=1200
   │   └─ Returns: doctrine (6 sections)
   │
   └─ tactician_prompt = TACTICIAN_PROMPT_TEMPLATE.format(mission=task, doctrine=doctrine)

3. Initialize AgentState
   ├─ state.task = task
   ├─ state.screenshot = png
   ├─ state.screen_dims = (sw, sh)
   ├─ state.strategist_doctrine = doctrine
   ├─ state.tactician_prompt = tactician_prompt
   ├─ state.current_executor_prompt = None (not yet configured)
   ├─ state.current_phase = "INIT"
   └─ state.current_tool_names = []

4. Enter run_agent(state) main loop
```

### Turn Execution (Detailed Flow)

**Every Turn (1 to MAX_STEPS=600):**

```
1. TURN INCREMENT
   state.increment_turn()  # state.turn += 1

2. SCREENSHOT CAPTURE
   png, sw, sh = capture_png(512, 256)
   ├─ GDI StretchBlt: Full screen → 512×256 (HALFTONE mode)
   ├─ draw_cursor(): Overlay cursor with hotspot offset
   ├─ RGB conversion: BGRA → RGB byte array
   └─ PNG encoding: IHDR + IDAT + IEND chunks

3. SCREENSHOT PERSISTENCE
   screenshot_path = save_screenshot(png, state.turn)
   # Saves to dumps/screen_0001.png, screen_0002.png, etc.
   state.update_screenshot(png)  # Update state.screenshot

4. TACTICIAN CHECK (turn==1 OR turn % 5 == 0)
   IF tactician_turn:
       (exec_prompt, phase, tools) = invoke_tactician(state)
       
       IF all three returned (not None):
           ├─ Print phase transition: INIT → RECONNAISSANCE
           ├─ state.update_executor_context(exec_prompt, phase, tools)
           └─ Log tool count
       
       ELIF turn == 1:
           ├─ FALLBACK triggered (tactician failed)
           ├─ state.update_executor_context(
           │       EXECUTOR_FALLBACK_PROMPT,
           │       "FALLBACK",
           │       ["click_element", "press_key", "type_text", ...]
           │   )
           └─ Log warning
       
       ELSE:
           └─ Continue with existing configuration
       
       time.sleep(3.5)  # TIMING_TURN_DELAY

5. EXECUTOR ACTION (if state.current_executor_prompt exists)
   tool_call = invoke_executor(state)
   
   IF tool_call is None:
       ├─ Log warning
       ├─ time.sleep(3.5)
       └─ continue to next turn
   
   tool_name = tool_call["function"]["name"]
   tool_args = json.loads(tool_call["function"]["arguments"])
   justification = tool_args.get("justification", "")
   
   IF tool_name == "report_completion":
       ├─ evidence = tool_args.get("evidence")
       ├─ IF len(evidence) < 100: reject, continue
       ├─ Print mission complete banner
       └─ RETURN "Completed in N turns"
   
   result = execute_tool_action(tool_name, tool_args, sw, sh)
   # Returns: "Clicked: button_name" or "Error: ..."
   
   state.add_history(
       tool=tool_name,
       args=tool_args,
       justification=justification,
       result=result,
       screenshot_path=screenshot_path
   )
   
   state.history = prune_history(state.history, 10)

6. TURN DELAY
   time.sleep(3.5)  # TIMING_TURN_DELAY
   └─ Loop continues
```

### Phase Transitions (Tactical Example)

**Scenario**: Calculator mission transitions from reconnaissance to execution.

```
Turn 1 (Reconnaissance Phase):
├─ Tactician oversight triggered
├─ Screenshot shows desktop
├─ invoke_tactician() returns:
│   ├─ spawn_executor_prompt: "You are in RECONNAISSANCE phase. Locate calculator app..."
│   ├─ phase: "RECONNAISSANCE"
│   └─ update_phase_tools: ["click_element", "scroll_down", "press_key"]
├─ state.update_executor_context() called
└─ Executor limited to 3 tools (no report_completion)

Turns 2-5 (Execution):
├─ Executor navigates Start menu with 3 tools
├─ No tactician oversight (autonomous operation)
└─ Actions: click Start → type "calc" → click result

Turn 6 (Phase Transition):
├─ Tactician oversight triggered
├─ Screenshot shows calculator open
├─ invoke_tactician() detects phase completion:
│   ├─ spawn_executor_prompt: "You are in EXECUTION phase. Perform calculation..."
│   ├─ phase: "EXECUTION_CALCULATOR"
│   └─ update_phase_tools: ["click_element", "type_text"]
└─ Executor reconfigured with 2 tools

Turns 7-11 (Calculation):
├─ Executor clicks number buttons
└─ Autonomous execution

Turn 12 (Verification):
├─ Tactician sees result displayed
├─ spawn_executor_prompt: "VERIFICATION phase - confirm result..."
├─ update_phase_tools: ["click_element", "report_completion"]
└─ report_completion NOW available

Turn 13:
├─ Executor calls report_completion with visual evidence
└─ Mission complete
```

### Completion Detection

**Trigger**: Executor calls `report_completion` tool.

**Validation**:
```python
if tool_name == "report_completion":
    evidence = tool_args.get("evidence", "")
    if len(evidence.strip()) < 100:
        # Reject insufficient evidence
        print("✗ Insufficient completion evidence")
        continue  # Skip turn, do not complete
```

**Success Path**:
1. Print mission complete banner (70-char ASCII border)
2. Print evidence text
3. Return `f"Completed in {state.turn} turns"` from `run_agent()`
4. Main prints debrief (total turns, final phase, archive size)

**Critical Constraint**: `report_completion` tool MUST be explicitly added by tactician via `update_phase_tools` (not available by default). This prevents premature completion during reconnaissance/execution phases.

---

## 4. DEPENDENCY MAPPING

### LM Studio API Contract

**Endpoint**: `http://localhost:1234/v1/chat/completions`

**Request Payload** (OpenAI-compatible):
```json
{
  "model": "qwen3-vl-2b-instruct",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": [
      {"type": "text", "text": "..."},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
    ]}
  ],
  "tools": [  // Optional (omitted for strategist)
    {
      "type": "function",
      "function": {
        "name": "tool_name",
        "description": "...",
        "parameters": { "type": "object", "properties": {...} }
      }
    }
  ],
  "tool_choice": "auto",  // Or "none" (not used in code)
  "temperature": 0.3-0.75,
  "max_tokens": 800-1200
}
```

**Response Structure**:
```json
{
  "choices": [
    {
      "message": {
        "content": "Text response (if no tools)",
        "tool_calls": [  // If tools invoked
          {
            "function": {
              "name": "click_element",
              "arguments": "{\"label\":\"Start\",\"position\":[50,950],\"justification\":\"...\"}"
            }
          }
        ]
      }
    }
  ]
}
```

**Function Calling Schema**: OpenAI-compatible JSON schema validation (no regex parsing in code).

**Stateless Requirement**: Each request must contain full context (no conversation_id or session management).

**Image Token Budget**: Image tokens NOT counted toward 12K text token limit (handled separately by model).

### Windows API Usage

**DPI Awareness** (CRITICAL - must be first API call):
```python
user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
# Value: -4 (enables physical pixel coordinates on high-DPI displays)
```

**Screen Size Query**:
```python
user32.GetSystemMetrics(SM_CXSCREEN)  # 0 = width
user32.GetSystemMetrics(SM_CYSCREEN)  # 1 = height
# Returns physical pixels (e.g., 1920×1080, 3840×2160)
```

**Screenshot Capture (GDI)**:
```python
# 1. Get screen DC
hdc_scr = user32.GetDC(None)  # None = entire screen

# 2. Create memory DC
hdc_mem = gdi32.CreateCompatibleDC(hdc_scr)

# 3. Create DIB section (target size: 512×256)
bmi = BITMAPINFO()
bmi.bmiHeader.biWidth = 512
bmi.bmiHeader.biHeight = -256  # Negative = top-down bitmap
bmi.bmiHeader.biBitCount = 32  # BGRA format
hbm = gdi32.CreateDIBSection(hdc_scr, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)

# 4. Select bitmap into memory DC
old = gdi32.SelectObject(hdc_mem, hbm)

# 5. Set stretch mode (CRITICAL for quality)
gdi32.SetStretchBltMode(hdc_mem, HALFTONE)  # 4 = high-quality downsampling
gdi32.SetBrushOrgEx(hdc_mem, 0, 0, None)    # Reset brush origin for HALFTONE

# 6. Stretch blit full screen → target size
gdi32.StretchBlt(
    hdc_mem, 0, 0, 512, 256,  # Destination
    hdc_scr, 0, 0, sw, sh,    # Source (full screen)
    SRCCOPY  # 0x00CC0020 = copy pixels
)

# 7. Draw cursor overlay
draw_cursor(hdc_mem, sw, sh, 512, 256)

# 8. Read pixel data from DIB bits
raw = bytes((ctypes.c_ubyte * (512 * 256 * 4)).from_address(bits.value))

# 9. Cleanup (CRITICAL to prevent GDI leaks)
gdi32.SelectObject(hdc_mem, old)
gdi32.DeleteObject(hbm)
gdi32.DeleteDC(hdc_mem)
user32.ReleaseDC(None, hdc_scr)
```

**Cursor Drawing**:
```python
ci = CURSORINFO(cbSize=ctypes.sizeof(CURSORINFO))
user32.GetCursorInfo(ctypes.byref(ci))  # Get cursor state
if ci.flags & CURSOR_SHOWING:
    ii = ICONINFO()
    user32.GetIconInfo(ci.hCursor, ctypes.byref(ii))  # Get hotspot
    cx = ci.ptScreenPos.x - ii.xHotspot  # Adjust for hotspot
    dx = round(cx * (dw / sw))           # Scale to target size
    user32.DrawIconEx(hdc_mem, dx, dy, ci.hCursor, 0, 0, 0, None, DI_NORMAL)
    gdi32.DeleteObject(ii.hbmMask)       # Cleanup icon bitmaps
    gdi32.DeleteObject(ii.hbmColor)
```

**Mouse Control**:
```python
user32.SetCursorPos(px, py)  # Instant teleport (no animation)
```

**SendInput API** (mouse clicks):
```python
inputs = [
    INPUT(type=INPUT_MOUSE, ii=INPUT_I(mi=MOUSEINPUT(
        dx=0, dy=0,
        mouseData=0,  # Not used for clicks
        dwFlags=MOUSEEVENTF_LEFTDOWN,  # 0x0002
        time=0,  # System timestamp
        dwExtraInfo=0
    ))),
    INPUT(type=INPUT_MOUSE, ii=INPUT_I(mi=MOUSEINPUT(
        dwFlags=MOUSEEVENTF_LEFTUP  # 0x0004
    )))
]
user32.SendInput(len(inputs), (INPUT * len(inputs))(*inputs), ctypes.sizeof(INPUT))
```

**SendInput API** (keyboard):
```python
# Unicode text (supports all characters)
for ch in text:
    code = ord(ch)
    inputs = [
        INPUT(type=INPUT_KEYBOARD, ii=INPUT_I(ki=KEYBDINPUT(
            wVk=0,  # Virtual key not used
            wScan=code,  # Unicode codepoint
            dwFlags=KEYEVENTF_UNICODE,  # 0x0004
            time=0,
            dwExtraInfo=0
        ))),
        INPUT(type=INPUT_KEYBOARD, ii=INPUT_I(ki=KEYBDINPUT(
            wScan=code,
            dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP  # 0x0006
        )))
    ]
```

**Scroll Wheel**:
```python
INPUT(type=INPUT_MOUSE, ii=INPUT_I(mi=MOUSEINPUT(
    mouseData=120,  # +120 = scroll UP, -120 = scroll DOWN
    dwFlags=MOUSEEVENTF_WHEEL  # 0x0800
)))
```

### Cross-Component Calls

**Invocation Chain**:
```
main()
  ├─ invoke_strategist() → doctrine
  ├─ run_agent(state)
  │   ├─ capture_png() → (png, sw, sh)
  │   ├─ invoke_tactician(state) → (prompt, phase, tools)
  │   ├─ invoke_executor(state) → tool_call
  │   ├─ execute_tool_action(name, args, sw, sh) → result
  │   └─ state.add_history()
  └─ Print debrief
```

**Tool Call Parsing** (JSON schema validation):
```python
# No regex parsing - LM Studio enforces schema
tool_call = resp["choices"][0]["message"]["tool_calls"][0]
tool_name = tool_call["function"]["name"]
tool_args = json.loads(tool_call["function"]["arguments"])  # May raise JSONDecodeError
```

**Error Propagation**:
- `post_json()`: Prints error, re-raises exception
- `invoke_*()`: Returns fallback values (empty string, None tuple)
- `execute_tool_action()`: Returns "Error: ..." string (no exception)
- Main loop: Catches `KeyboardInterrupt` (saves checkpoint), re-raises other exceptions

---

## 5. CONFIGURATION ANALYSIS

### Timing Constants (Rationale)

**`TIMING_CURSOR_SETTLE = 0.12`** (120ms):
- **Purpose**: Wait for `SetCursorPos()` to complete before mouse action
- **Rationale**: Windows cursor positioning is not synchronous; immediate click may miss target
- **Risk**: Insufficient on slow systems (Remote Desktop, VM, low-end CPU)

**`TIMING_UI_RENDER = 2.5`** (2500ms):
- **Purpose**: Wait for UI to update after action (click, type, scroll)
- **Rationale**: Desktop apps may have render delays (animations, network fetch, disk I/O)
- **Assumption**: 2.5s covers 95% of typical UI updates (worst-case: browser page load)
- **Risk**: Insufficient for slow web apps (JS-heavy SPAs, slow network)

**`TIMING_INPUT_CHAR = 0.005`** (5ms):
- **Purpose**: Delay between typed characters
- **Rationale**: Some apps cannot handle instant text input (keylogger detection, input validation)
- **Performance**: 5ms × 100 chars = 0.5s overhead (acceptable)

**`TIMING_CLICK_DOUBLE = 0.05`** (50ms):
- **Purpose**: Delay between two clicks in `double_click()`
- **Rationale**: Windows double-click threshold is ~500ms, but apps may require faster succession
- **Risk**: May be too fast for some apps (should be 100-200ms for reliability)

**`TIMING_DRAG_STEP = 0.01`** (10ms):
- **Purpose**: Delay between drag interpolation steps (20 steps total)
- **Rationale**: Smooth drag simulation = 20 steps × 10ms = 200ms total
- **Performance**: Prevents instant teleport (some apps detect non-human drags)

**`TIMING_DRAG_PREPARE = 0.1`** (100ms):
- **Purpose**: Settle delay after moving to drag start position
- **Rationale**: Ensures cursor is positioned before mouse down

**`TIMING_SCREENSHOT_SETTLE = 3.4`** (3400ms):
- **Purpose**: Wait before capturing screenshot (allows UI to render)
- **Composition**: `TIMING_UI_RENDER (2.5s)` + buffer (0.9s)
- **Rationale**: Ensures screenshot reflects completed UI state
- **Risk**: May still be insufficient for slow systems

**`TIMING_TURN_DELAY = 3.5`** (3500ms):
- **Purpose**: Minimum delay between turns (prevents runaway loops)
- **Rationale**: Gives UI time to stabilize + prevents excessive API calls
- **Composition**: Slightly longer than `TIMING_SCREENSHOT_SETTLE` to ensure non-overlapping captures
- **Risk**: Fixed delay wastes time on fast operations (no adaptive timing)

### Hierarchy Configuration

**`TACTICIAN_INTERVAL = 5`**:
- **Purpose**: Oversight frequency (every 5 turns)
- **Rationale**: Balance between adaptability and efficiency
  - **Too frequent (1-2 turns)**: Excessive LLM calls, slow execution
  - **Too infrequent (20+ turns)**: Slow adaptation to UI changes, executor may drift
- **Comparison to Original**: Original system used 30-turn replanning (6× less frequent)
- **Token Cost**: Tactician call (~800 tokens) every 5 turns vs. executor call (~1024 tokens) every turn
- **Design Trade-off**: More oversight = faster error correction, but higher cost

**`JUSTIFICATION_MIN_CHARS = 30`**:
- **Purpose**: Minimum justification length (not enforced in code, only in prompt)
- **Rationale**: Forces LLM to articulate reasoning (improves action quality)
- **Actual Enforcement**: Tool descriptions specify "30-50 words" (converted to chars ~150-300)

### History Configuration

**`MAX_HISTORY_ITEMS = 10`**:
- **Purpose**: Maximum history entries retained in memory
- **Rationale**: 
  - **LLM Context**: Last 8 actions sent (compact format ~100 chars each = 800 chars)
  - **Loop Detection**: Needs at least 5 recent actions
  - **Token Budget**: 10 items = ~1000 chars (safe within 12K limit)
- **Truncation**: Simple FIFO (oldest dropped first, no priority tiers)

**History Format** (sent to LLM):
```
MISSION: [task description]

DOCTRINE:
[First 400 chars of strategist output]...

CURRENT PHASE: EXECUTION_NOTEPAD

RECENT ACTIONS:
  T5: click_element(Start Menu) → Clicked: Start Menu
  T6: type_text(notepad) → Typed: notepad
  T7: click_element(Notepad - Desktop app) → Clicked: Notepad - Desktop app
  ...
```

### Loop Detection

**`LOOP_DETECTION_THRESHOLD = 3`**:
- **Purpose**: Repeated action count triggering loop warning
- **Mechanism**: Signature-based matching (tool name + label)
  ```python
  last_sig = (last["tool"], last["args"].get("label", ""))
  matches = sum(1 for h in recent[-5:] if (h["tool"], h["args"].get("label")) == last_sig)
  if matches >= 3:
      # Loop detected
  ```
- **Response**:
  1. **In-context warning**: "⚠️ LOOP: click_element on 'Start' repeated 3× - CHANGE APPROACH ⚠️"
  2. **Temperature boost**: 0.5 → 0.75 (increases randomness)
- **Limitation**: Only detects exact label matches (ignores position, text, key)

### Screenshot Resolution

**`AGENT_IMAGE_W = 512`**, **`AGENT_IMAGE_H = 256`**:
- **Purpose**: Target screenshot dimensions for testing
- **Rationale**:
  - Low resolution = faster API transmission (PNG ~50-100 KB)
  - Qwen3-VL 2B can process small images adequately
  - Reduces image token count (more budget for text)
- **Production Setting**: 1536×864 (3× larger, ~16:9 aspect)
- **Trade-off**: Small UI elements (buttons, text) may be unreadable at 512×256

---

## 6. COORDINATE SYSTEM SPECIFICATION

### Normalization (0-1000 Scale)

**Design Rationale**:
- **LLM-Friendly**: Integer coordinates easier for small models than floats (0.0-1.0)
- **Precision**: 0.001 fractional precision (1/1000) = ±0.5 pixel error on 1920px screen
- **Consistency**: Same scale regardless of physical resolution (works on 1080p, 4K, ultrawide)

**Coordinate Space**:
```
(0, 0) ───────────────────────── (1000, 0)
  │                                   │
  │        Screen Area                │
  │                                   │
(0, 1000) ─────────────────── (1000, 1000)
```

**Example Mappings** (1920×1080 screen):
- `[0, 0]` → (0, 0) pixels (top-left corner)
- `[500, 500]` → (960, 540) pixels (center)
- `[1000, 1000]` → (1919, 1079) pixels (bottom-right corner)
- `[250, 950]` → (480, 1026) pixels (bottom-left quadrant)

### Transformation Math

**Implementation** (`norm_to_px` function):
```python
def norm_to_px(xn: float, yn: float, sw: int, sh: int) -> Tuple[int, int]:
    # 1. Clamp to valid range [0, 1000]
    xn = max(0.0, min(1000.0, xn))
    yn = max(0.0, min(1000.0, yn))
    
    # 2. Scale to physical pixels
    px = (xn / 1000.0) * sw  # Example: (500 / 1000) * 1920 = 960.0
    py = (yn / 1000.0) * sh
    
    # 3. Round to integer
    px = round(px)  # 960.0 → 960
    py = round(py)
    
    # 4. Clamp to screen bounds [0, sw-1]
    px = min(px, sw - 1)  # Prevent overflow (max pixel = 1919 on 1920px screen)
    py = min(py, sh - 1)
    
    return (px, py)
```

**Precision Analysis**:
- **Rounding Error**: ±0.5 pixel maximum (from `round()`)
- **Boundary Safety**: `min(px, sw-1)` prevents off-screen coordinates
- **Clamping**: Invalid inputs (e.g., 1500, -50) are corrected to (1000, 0)

**Example Calculations** (1920×1080):
```
Input [500, 500] (center):
  px = round((500 / 1000) * 1920) = round(960.0) = 960
  py = round((500 / 1000) * 1080) = round(540.0) = 540
  → (960, 540) ✓ Exact center

Input [333, 666]:
  px = round((333 / 1000) * 1920) = round(639.36) = 639
  py = round((666 / 1000) * 1080) = round(719.28) = 719
  → (639, 719) ✓ Within ±0.5px error

Input [1000, 1000] (corner):
  px = round((1000 / 1000) * 1920) = 1920
  py = round((1000 / 1000) * 1080) = 1080
  px = min(1920, 1919) = 1919  # Clamped
  py = min(1080, 1079) = 1079
  → (1919, 1079) ✓ Valid corner pixel
```

### High-DPI Handling

**DPI Awareness Context**:
```python
user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
# -4 = PER_MONITOR_AWARE_V2 (most accurate mode)
```

**Awareness Levels**:
1. **UNAWARE** (default): Windows scales coordinates (e.g., 4K screen reports 1920×1080)
2. **SYSTEM_AWARE**: Single DPI for all monitors (incorrect on mixed-DPI setups)
3. **PER_MONITOR_AWARE**: Per-monitor DPI, but no automatic scaling
4. **PER_MONITOR_AWARE_V2**: Per-monitor + child window scaling (BEST)

**Why V2 is Critical**:
- **Physical Pixels**: `GetSystemMetrics(SM_CXSCREEN)` returns true resolution (3840×2160, not 1920×1080)
- **Coordinate Accuracy**: `SetCursorPos(x, y)` uses physical pixels (no scaling confusion)
- **Mixed DPI**: Correctly handles 4K primary + 1080p secondary monitors

**High-DPI Example** (3840×2160 screen):
```
Normalized [500, 500] (center):
  px = round((500 / 1000) * 3840) = 1920
  py = round((500 / 1000) * 2160) = 1080
  → (1920, 1080) ✓ Exact center of 4K screen

Without DPI awareness:
  GetSystemMetrics returns 1920×1080 (scaled)
  px = round((500 / 1000) * 1920) = 960
  → (960, 540) ✗ Wrong position (top-left quadrant instead of center)
```

### Precision Limitations

**Rounding Error**: ±0.5 pixel maximum from `round()` function.

**Subpixel Coordinates Not Supported**:
- Windows API uses integer pixels only
- Fractional coordinates like `[500.5, 500.5]` are rounded
- No antialiasing or subpixel precision

**Small Target Accuracy** (512×256 test resolution):
- 10px button at 1920×1080 → ~2.7px in screenshot
- LLM must estimate center within ±1-2 normalized units (~2-4 physical pixels)
- **Risk**: Small buttons may be unmissable at low resolution

**Production Resolution** (1536×864):
- 10px button → ~8px in screenshot (3× larger)
- Better target visibility for 2B vision model

---

## 7. TIMING SUBSYSTEM

### UI Stabilization

**`TIMING_UI_RENDER = 2.5s`**:

**Assumptions**:
- **Desktop apps**: 50-500ms render time (menus, dialogs, animations)
- **Web browsers**: 500-2000ms page load (JS execution, network fetch)
- **Worst-case**: 2.5s covers 95th percentile of UI updates

**Use Cases**:
- After `click()`: Wait for menu to open, dialog to appear
- After `type_text()`: Wait for autocomplete dropdown, search results
- After `scroll_action()`: Wait for lazy-loaded content

**Insufficiency Scenarios**:
1. **Slow web apps**: React/Angular SPAs with heavy JS bundles (3-5s load)
2. **Network-dependent UI**: Dropdowns fetching data from slow API
3. **Video rendering**: Media apps (VLC, Premiere) may need 5-10s
4. **System under load**: High CPU/disk usage delays rendering

**No Adaptive Timing**: Fixed 2.5s delay regardless of actual render time (wastes time on fast operations).

### Cursor Positioning

**`TIMING_CURSOR_SETTLE = 0.12s`** (120ms):

**Purpose**: Wait for `SetCursorPos()` to complete before executing action.

**Windows API Behavior**:
- `SetCursorPos()` is **not synchronous**—it queues a request to move cursor
- Actual move happens in next input processing cycle (10-50ms typical)
- Immediate `SendInput()` may occur before cursor reaches target

**Risk Scenarios**:
1. **Remote Desktop**: Cursor updates delayed by network latency (100-300ms)
2. **Virtual machines**: Cursor may lag by 50-200ms
3. **Low-end hardware**: Slow input processing (rare on modern systems)

**Evidence of Insufficiency**:
- If clicks miss targets despite correct coordinates, increase to 200-300ms
- Logs would show "Clicked: button" but no visible action

### Screenshot Delay

**`TIMING_SCREENSHOT_SETTLE = 3.4s`**:

**Composition**:
- `TIMING_UI_RENDER (2.5s)` + buffer (0.9s)

**Purpose**: Ensure screenshot captures fully rendered UI state after action.

**Rationale**:
- Action executes → UI_RENDER wait (2.5s) → screenshot capture
- Buffer (0.9s) accounts for screenshot capture overhead (~100ms) + safety margin

**Race Condition Risk**:
- If UI takes >2.5s to render, screenshot may capture intermediate state
- Example: Click "Save" → file dialog appears in 3.2s → screenshot at 3.4s shows loading state

**Not Used in Code**: This constant is defined but never referenced—screenshot capture has NO explicit settle delay. Actual delay is only `TIMING_TURN_DELAY (3.5s)` at end of turn.

### Turn Delay

**`TIMING_TURN_DELAY = 3.5s`**:

**Purpose**:
1. **Runaway loop prevention**: Prevents agent from executing 100s of actions/second
2. **UI stabilization**: Gives system time to complete all pending operations
3. **Rate limiting**: Reduces LLM API call frequency

**Composition**:
- Slightly longer than `TIMING_SCREENSHOT_SETTLE` to ensure non-overlapping captures

**Inefficiency**:
- Fixed delay wastes time on fast operations (e.g., typing "a" takes 2.5s UI render + 3.5s turn delay = 6s total)
- No adaptive timing based on action type (click vs. drag vs. type)

**Optimal Strategy** (not implemented):
```python
# Adaptive per-action delays
ACTION_DELAYS = {
    "click_element": 1.0,
    "type_text": 0.5,
    "press_key": 0.8,
    "drag_element": 2.0,
    "scroll_down": 0.3
}
time.sleep(ACTION_DELAYS.get(tool_name, 3.5))
```

### Race Condition Analysis

**Issue 1: Screenshot Capture Has No Settle Delay**

**Code Path**:
```python
# execute_tool_action() includes:
time.sleep(TIMING_UI_RENDER)  # 2.5s wait after action

# But then immediately:
png, sw, sh = capture_png(512, 256)  # No additional delay!
```

**Risk**: If UI takes 2.6s to render, screenshot captures incomplete state.

**Fix**: Add explicit delay before capture:
```python
time.sleep(TIMING_SCREENSHOT_SETTLE - TIMING_UI_RENDER)  # 0.9s additional
png, sw, sh = capture_png(512, 256)
```

**Issue 2: Cursor Settle Not Applied Before All Mouse Actions**

**Vulnerable Code** (in `drag_element`):
```python
move_mouse(x1, y1)
time.sleep(TIMING_DRAG_PREPARE)  # 0.1s (insufficient)
send_input([LEFTDOWN])
```

**Risk**: 100ms may be insufficient on slow systems (should use `TIMING_CURSOR_SETTLE = 0.12s`).

**Issue 3: Scroll Position Before Scroll Action**

**Code**:
```python
def scroll_action(direction: int):
    move_mouse(sw // 2, sh // 2)  # Move to center
    time.sleep(TIMING_CURSOR_SETTLE)  # ✓ Settle delay
    scroll_action(direction)  # ✓ Correct
```

**No Issue**: Correctly applies settle delay before scroll.

**Issue 4: Double-Click Timing Too Fast**

**Code**:
```python
def double_click():
    click()
    time.sleep(TIMING_CLICK_DOUBLE)  # 50ms
    click()
```

**Risk**: 50ms is faster than typical double-click threshold (200-500ms). Some apps may not recognize as double-click.

**Fix**: Increase to 100-150ms for reliability.

---

## 8. TOOL EXECUTION FRAMEWORK

### Tactician Meta-Tools

**`spawn_executor_prompt`**:

**Purpose**: Dynamically create executor system prompt for current phase.

**Parameters**:
- `prompt` (string, 200-400 words): Complete system prompt including:
  - Phase goals (e.g., "Locate calculator app in Start menu")
  - Precision requirements (e.g., "Click center of buttons, not edges")
  - Risk warnings (from strategist, e.g., "Dropdown closes in 2s")
  - Coordinate system reminder ("0-1000 scale, [x,y] format")
  - Justification requirements ("50+ word justification per action")
- `phase` (string): Phase identifier (e.g., "RECONNAISSANCE", "EXECUTION_NOTEPAD")
- `rationale` (string, 50-100 words): Why this update is needed

**Execution Flow**:
1. Tactician LLM generates tool call: `{"name": "spawn_executor_prompt", "arguments": "{...}"}`
2. `invoke_tactician()` extracts `prompt`, `phase`, `rationale` from arguments
3. Prints rationale to console: `"✓ Executor prompt spawned for phase: RECONNAISSANCE"`
4. Returns `(prompt, phase, None)` (tool_names from separate call)
5. Main loop calls `state.update_executor_context(prompt, phase, tools)`

**Not Available to Executor**: Only tactician can spawn prompts (prevents self-modification).

**`update_phase_tools`**:

**Purpose**: Specify tool name whitelist for executor (phase-based subsetting).

**Parameters**:
- `tool_names` (array of strings): List of tool names to enable (e.g., `["click_element", "press_key"]`)
- `rationale` (string, 50 words): Why these specific tools

**Execution Flow**:
1. Tactician generates: `{"name": "update_phase_tools", "arguments": "{\"tool_names\": [...]}"}`
2. `invoke_tactician()` extracts `tool_names`, `rationale`
3. Prints: `"✓ Tools updated: ['click_element', 'press_key', 'report_completion']"`
4. Returns `(None, None, tool_names)`
5. Main loop calls `state.update_executor_context(..., tool_names)`
6. Executor invocation uses `state.get_executor_tools()` → filters `TOOL_REGISTRY`

**Critical Rule**: `"report_completion"` must be explicitly included by tactician—not available by default.

### Executor Action Tools

**`report_completion`**:
- **Availability**: ONLY when tactician adds to `tool_names`
- **Parameters**: `evidence` (string, 100 words) - visual proof of completion
- **Execution**: Prints mission complete banner, returns completion message
- **Validation**: Rejects if `len(evidence.strip()) < 100`

**Click Tools** (`click_element`, `double_click_element`, `right_click_element`):
- **Common Parameters**:
  - `justification` (string, 30-50 words)
  - `label` (string): Element name (e.g., "Start button")
  - `position` (array[2]): Center point `[x, y]` in 0-1000 scale
- **Execution**:
  1. `norm_to_px()` converts position to physical pixels
  2. `move_mouse(px, py)` teleports cursor
  3. `time.sleep(TIMING_CURSOR_SETTLE)` waits 120ms
  4. `click()` / `double_click()` / `right_click()` sends input events
  5. `time.sleep(TIMING_UI_RENDER)` waits 2.5s
- **Return**: `"Clicked: [label]"` or `"Error: label and position required"`

**`drag_element`**:
- **Parameters**: `justification`, `label`, `start` [x,y], `end` [x,y]
- **Execution**:
  1. Convert start/end to pixels
  2. `move_mouse(start)` + settle delay
  3. Send LEFTDOWN event
  4. Interpolate 20 steps from start to end (10ms per step = 200ms total)
  5. Send LEFTUP event
  6. UI render delay
- **Use Cases**: Window resizing, slider adjustment, drawing

**`type_text`**:
- **Parameters**: `justification`, `text` (string)
- **Execution**:
  - Sends Unicode keyboard events (supports all characters, emojis, etc.)
  - 5ms delay between characters (100 chars = 0.5s)
  - No automatic focus check (assumes target field is already focused)
- **Risk**: If wrong window focused, text goes to wrong app

**`press_key`**:
- **Parameters**: `justification`, `key` (string) - e.g., "enter", "ctrl+c", "windows"
- **Validation**: Checks all key parts exist in `VK_MAP` (returns error if unknown)
- **Execution**:
  1. Split combo: `"ctrl+c"` → `["ctrl", "c"]`
  2. Map to VK codes: `[0x11, 0x43]`
  3. Send KEYDOWN events in order: ctrl → c
  4. Send KEYUP events in reverse: c → ctrl
- **Supported Keys**: 26 keys in `VK_MAP` (enter, tab, esc, function keys, arrows, etc.)

**`scroll_down` / `scroll_up`**:
- **Parameters**: `justification` only
- **Execution**:
  1. Move mouse to screen center: `(sw // 2, sh // 2)`
  2. Settle delay
  3. Send wheel event: `mouseData=+120` (up) or `-120` (down)
  4. UI render delay
- **Scroll Direction**: +120 = UP, -120 = DOWN (standard Windows convention)

### Validation

**JSON Schema Enforcement**:
- LM Studio API validates tool calls against OpenAI function schemas
- No manual regex parsing in code
- Invalid tool calls rejected by API (not returned in response)

**Client-Side Validation** (`execute_tool_action`):
```python
if name in CLICK_TOOLS_MAP:
    if not label or not position or len(position) != 2:
        return "Error: label and position [x,y] required"
```

**Justification Validation**:
- Length requirement specified in tool descriptions (30-50 words)
- NOT enforced in code (LLM responsible for compliance)
- Short justifications accepted without error

### Execution Sequence

**Full Action Sequence** (example: click button):
```
1. Executor LLM call returns:
   {
     "name": "click_element",
     "arguments": {
       "label": "Start",
       "position": [50, 950],
       "justification": "Desktop visible with Start button at bottom-left. Clicking to open Start menu for app navigation. Expect menu to appear in 1s."
     }
   }

2. Main loop extracts tool_call[0]

3. execute_tool_action("click_element", args, sw=1920, sh=1080):
   a. Validate: label="Start", position=[50, 950] ✓
   b. norm_to_px(50, 950, 1920, 1080) → (96, 1026)
   c. move_mouse(96, 1026)  # Instant teleport
   d. time.sleep(0.12)       # Cursor settle
   e. click()                # LEFTDOWN + LEFTUP events
   f. time.sleep(2.5)        # UI render wait
   g. return "Clicked: Start"

4. Main loop:
   a. Print result: "✓ Clicked: Start"
   b. state.add_history(tool="click_element", args={...}, result="Clicked: Start")
   c. Prune history to 10 items
   d. time.sleep(3.5)        # Turn delay

5. Next turn:
   a. Capture screenshot (Start menu now visible)
   b. Send to executor
```

### Single-Action Enforcement

**Implementation**:
```python
tool_calls = msg.get("tool_calls")
if not tool_calls:
    return None

# CRITICAL: Only first tool call executed
return tool_calls[0]  # No loop over array
```

**Rationale**:
- **Prevents error cascades**: If action 1 fails, action 2-5 would compound the error
- **Improves observability**: One action = one screenshot = clear cause-effect
- **Simplifies debugging**: No need to track which action in chain failed

**Trade-offs**:
- **Slower execution**: Multi-step tasks require multiple turns
- **More LLM calls**: 5 actions = 5 API requests instead of 1
- **Higher token cost**: Each turn resends full context (history, screenshot, doctrine)

**Example Impact**:
- Task: Type "hello" and press enter
- **With chaining**: 1 turn (2 tool calls)
- **Single-action**: 2 turns (turn 1: type "hello", turn 2: press "enter")

---

## 9. CONTEXT MANAGEMENT

### History Storage

**Structure** (`state.history` list of dicts):
```python
{
    "turn": 5,
    "tool": "click_element",
    "args": {"label": "Start", "position": [50, 950], "justification": "..."},
    "result": "Clicked: Start",
    "screenshot": "dumps/screen_0005.png"
}
```

**Pruning Mechanism**:
```python
def prune_history(history: List[Dict], max_items: int) -> List[Dict]:
    if len(history) <= max_items:
        return history
    return history[-max_items:]  # Keep last N items only
```

**Pruning Frequency**: After every action (not batched).

**No Priority Tiers**: All actions treated equally—no special handling for phase transitions, errors, or critical actions.

**Full Archive** (optional):
- If `ENABLE_FULL_ARCHIVE=True`: All actions saved to `state.full_archive`
- Never pruned (grows unbounded)
- Saved to JSON checkpoint on Ctrl+C

### Doctrine Transmission

**Strategist Output**:
- Invoked once at startup
- Saved to `state.strategist_doctrine` (immutable)
- Full doctrine (6 sections, ~800-1200 words)

**Tactician Context**:
- Receives full doctrine in system prompt:
  ```python
  tactician_prompt = TACTICIAN_PROMPT_TEMPLATE.format(
      mission=task,
      doctrine=strategist_output  # Full 1200 words
  )
  ```
- Doctrine transmitted EVERY oversight turn (not cached by API)

**Executor Context**:
- Does NOT receive doctrine directly
- Receives phase-specific guidance via dynamically spawned prompt
- Implicitly follows doctrine through tactician's instructions

**History Text** (sent to tactician/executor):
```python
def build_history_text(state: AgentState) -> str:
    lines = [f"MISSION: {state.task}\n"]
    
    if state.strategist_doctrine:
        lines.append(f"DOCTRINE:\n{state.strategist_doctrine[:400]}...")  # Truncated
    
    lines.append(f"CURRENT PHASE: {state.current_phase}\n")
    lines.append("RECENT ACTIONS:")
    
    for h in state.history[-8:]:  # Last 8 only
        target = h['args'].get('label', h['args'].get('text', ''))[:30]
        outcome = h['result'][:60]
        lines.append(f"  T{h['turn']}: {h['tool']}({target}) → {outcome}")
    
    return "\n".join(lines)
```

**Doctrine Truncation**: Only first 400 chars sent in history context (full version in tactician system prompt).

### Loop Detection

**Mechanism** (`detect_terminal_loop` function):
```python
def detect_terminal_loop(state: AgentState) -> bool:
    if len(state.history) < 4:
        return False
    
    recent = state.history[-5:]  # Last 5 actions
    last = recent[-1]
    last_sig = (last["tool"], last["args"].get("label", ""))  # Signature tuple
    
    matches = sum(1 for h in recent if (h["tool"], h["args"].get("label")) == last_sig)
    
    return matches >= LOOP_DETECTION_THRESHOLD  # 3
```

**Signature Components**:
- Tool name (e.g., `"click_element"`)
- Label argument (e.g., `"Start"`)

**NOT Considered**:
- Position (clicking same label at different positions = same signature)
- Text content (typing different text = different signature)
- Justification (ignored)

**Response to Loop**:
1. **In-Context Warning** (appended to history text):
   ```
   ⚠️ LOOP: click_element on 'Start' repeated 3× - CHANGE APPROACH ⚠️
   ```
2. **Temperature Adjustment**:
   ```python
   temperature = LMSTUDIO_TEMPERATURE * 1.5  # 0.5 → 0.75
   ```

**Effectiveness**:
- **Works for**: Repeated clicks on same button, repeated key presses
- **Fails for**: Position-based loops (clicking different coordinates on same element), alternating patterns (A-B-A-B)

**Example Detection**:
```
T10: click_element(Start) → Clicked: Start
T11: click_element(Calculator) → Error: not found
T12: click_element(Start) → Clicked: Start
T13: click_element(Calculator) → Error: not found
T14: click_element(Start) → Clicked: Start  # 3rd repeat

Loop detected: (click_element, "Start") × 3
```

### Temperature Adjustment

**Base Temperature**:
- Strategist: 0.3 (deterministic planning)
- Tactician: 0.4 (balanced adaptation)
- Executor: 0.5 (precise actions)

**Loop Multiplier**: 1.5× (0.5 → 0.75)

**Effect of Higher Temperature**:
- Increases sampling randomness
- Reduces likelihood of repeating same action
- May reduce precision (coordinates, tool selection)

**Limitation**: No gradual increase (only 1-time boost, not 1.5× → 2.0× → 2.5×).

---

## 10. ERROR HANDLING REVIEW

### Tactician Failure Modes

**No Tool Calls Returned**:
```python
tool_calls = msg.get("tool_calls")
if not tool_calls:
    print(f"Tactician status: {msg.get('content', 'No updates')[:150]}")
    return (None, None, None)
```
- **Consequence**: Continue with existing executor configuration
- **Safe**: No reconfiguration needed if phase unchanged
- **Risk**: If phase DID change but tactician failed to spawn tools, executor operates with wrong tools

**Turn 1 Failure** (no initial configuration):
```python
if executor_prompt and phase_name and tool_names:
    state.update_executor_context(...)
elif state.turn == 1:
    # FALLBACK triggered
    state.update_executor_context(
        EXECUTOR_FALLBACK_PROMPT,
        "FALLBACK",
        ["click_element", "press_key", "type_text", "scroll_down", "scroll_up"]
    )
```
- **Trigger**: Tactician returns `(None, None, None)` on turn 1
- **Fallback**: Generic executor with 5 basic tools (no `report_completion`)
- **Risk**: No phase-specific guidance, no risk warnings from strategist

**Mid-Mission Failure** (turn > 1):
```python
if state.turn == 1:
    # Fallback logic
else:
    # No fallback - just continue
```
- **Consequence**: Executor continues with last known configuration
- **Safe**: Assumes previous configuration still valid
- **Risk**: If tactician detected critical phase change but failed to communicate, executor may perform wrong actions

**API Exception**:
```python
except Exception as e:
    print(f"Tactician call failed: {e}")
    return (None, None, None)
```
- **No retry**: Returns `(None, None, None)` immediately
- **Consequence**: Same as "no tool calls" case
- **Logged**: Error printed to console (not to file)

### Executor Failure Modes

**No Tool Calls Returned**:
```python
tool_calls = msg.get("tool_calls")
if not tool_calls:
    print(f"Executor returned no tool calls: {msg.get('content', '')[:100]}")
    return None
```
- **Main loop handling**:
  ```python
  if not tool_call:
      print("⚠️ No action taken this turn")
      time.sleep(TIMING_TURN_DELAY)
      continue  # Skip to next turn
  ```
- **Consequence**: Turn wasted, no history entry
- **Risk**: If executor consistently fails to generate tools, mission stalls

**JSON Parse Error**:
```python
try:
    tool_args = json.loads(tool_call["function"]["arguments"])
except json.JSONDecodeError as e:
    print(f"✗ Argument parse error: {e}")
    time.sleep(TIMING_TURN_DELAY)
    continue
```
- **Consequence**: Turn skipped, no action executed
- **Not recorded in history**: No evidence of failed parse

**Tool Execution Error**:
```python
result = execute_tool_action(tool_name, tool_args, sw, sh)
if result.startswith("Error:"):
    print(f"✗ {result}")
# STILL RECORDED IN HISTORY
state.add_history(tool=tool_name, args=tool_args, result=result, ...)
```
- **Example errors**:
  - `"Error: label and position [x,y] required"` (missing parameters)
  - `"Error: Unknown key 'ctrl+z'"` (invalid key name)
  - `"Error: unknown tool 'invalid_tool'"` (tool not in registry)
- **Consequence**: Error recorded, execution continues (no abort)
- **Visible to LLM**: Next turn's history includes error result

**API Exception**:
```python
except Exception as e:
    print(f"Executor call failed: {e}")
    return None
```
- **Main loop**: Treats as "no tool calls" case (skip turn)
- **No retry logic**: Single failure = lost turn

### API Errors

**`post_json` Function**:
```python
def post_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(req, timeout=LMSTUDIO_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"API failed: {e}")
        raise  # Re-raises exception
```

**No Automatic Retry**:
- Network errors (connection refused, timeout) → exception propagates
- HTTP errors (500, 503) → exception propagates
- Caller must handle exception

**Timeout Handling**:
- `LMSTUDIO_TIMEOUT = 240` seconds (4 minutes)
- Long timeout accommodates slow inference on 2B model
- If exceeded, `urllib.error.URLError` raised

**Caller Error Handling**:
- `invoke_strategist`: Returns error string (no exception)
- `invoke_tactician`: Returns `(None, None, None)` (catches exception)
- `invoke_executor`: Returns `None` (catches exception)

**No Exponential Backoff**: Single failure = immediate return (no 3-retry logic).

### Graceful Degradation Analysis

**Best-Case Failure Recovery**:
1. Executor fails to generate tool call (turn N)
2. Turn N skipped, screenshot captured
3. Turn N+1: Executor sees unchanged UI, retries action
4. Success

**Worst-Case Failure Cascade**:
1. Tactician fails to spawn executor on turn 1 (no fallback triggered due to bug)
2. Executor never configured (`current_executor_prompt = None`)
3. Every turn: "⚠️ Waiting for tactician initialization..."
4. Turn 6: Tactician oversight triggered, successfully spawns executor
5. Mission resumes

**No Persistent Failure Detection**:
- If executor fails 10 turns in a row, no special handling
- No automatic fallback to simpler tools
- No mission abort on repeated failures

---

## 11. CRITICAL DESIGN DECISIONS

### Tool-Based Prompt Spawning (vs. Regex Parsing)

**Implementation**:
- Tactician uses `spawn_executor_prompt` tool to generate executor prompts
- LLM outputs structured JSON: `{"name": "spawn_executor_prompt", "arguments": "{\"prompt\": \"...\"}"}`
- Code extracts via `json.loads()` (no regex)

**Rationale**:
1. **Type Safety**: JSON schema enforces parameter types (string, array, object)
2. **LLM Validation**: Model must generate valid JSON (API rejects malformed calls)
3. **Auditability**: Tool calls logged with rationale field (explicit reasoning)
4. **Extensibility**: Adding parameters requires schema update only (no regex rewrite)

**Alternative (Regex Parsing)**:
```python
# Hypothetical regex approach
prompt_match = re.search(r"EXECUTOR_PROMPT:\s*(.+?)END_PROMPT", tactician_output, re.DOTALL)
if prompt_match:
    executor_prompt = prompt_match.group(1)
```

**Trade-offs**:

| Aspect | Tool-Based | Regex-Based |
|--------|-----------|-------------|
| **Reliability** | High (schema-enforced) | Low (format drift, edge cases) |
| **LLM Burden** | Must learn tool calling | Natural text generation |
| **Parsing Complexity** | Simple (`json.loads`) | Complex (multiline regex, escaping) |
| **Failure Mode** | No tool call → explicit None | No match → silent failure |
| **Debugging** | Clear error messages | Regex debugging (cryptic) |
| **2B Model Capability** | Requires function calling support | Easier for small models |

**Decision Justification**: Tool-based approach chosen for reliability despite higher LLM burden. Small model (Qwen3-VL 2B) tested to support function calling adequately.

### Single-Action Execution (vs. Chaining)

**Implementation**:
```python
tool_calls = msg.get("tool_calls")
return tool_calls[0]  # Only first action
```

**Rationale**:
1. **Error Isolation**: If action 1 fails, actions 2-5 don't execute on wrong state
2. **Observability**: One action = one screenshot = clear cause-effect relationship
3. **Debugging**: No ambiguity about which action in chain caused issue
4. **Simplified Logic**: No need for "stop on first error" or "rollback" mechanisms

**Example Error Cascade (Chaining)**:
```
Action 1: click "File" → Success (menu opens)
Action 2: click "Save As" → Fails (menu closed due to timing)
Action 3: type "document.txt" → Types into wrong window (desktop, not dialog)
Action 4: press "enter" → Creates shortcut on desktop (wrong action)
```

**Single-Action Approach**:
```
Turn 1: click "File" → Success
Turn 2: Screenshot shows menu open
Turn 3: click "Save As" → Success
Turn 4: Screenshot shows dialog
Turn 5: type "document.txt" → Success in correct field
```

**Trade-offs**:

| Aspect | Single-Action | Chaining |
|--------|--------------|----------|
| **Execution Speed** | Slow (5 actions = 5 turns × 7s = 35s) | Fast (5 actions = 1 turn × 7s) |
| **Error Recovery** | Easy (retry next turn) | Hard (partial state rollback) |
| **Token Cost** | High (5× context resend) | Low (1× context) |
| **Max Actions** | Unlimited (bounded by MAX_STEPS) | Limited by tool_calls array size |
| **Observability** | High (screenshot per action) | Low (screenshot per batch) |

**Decision Justification**: Prioritizes **correctness and debuggability** over speed. For 2B model with limited reasoning, single-action reduces compounding errors.

### 5-Turn Oversight Interval (vs. 30-Turn Replanning)

**Implementation**: `TACTICIAN_INTERVAL = 5`

**Original System**: 30-turn replanning (strategist regenerates full plan every 30 turns).

**New System**: 5-turn oversight (tactician reassesses phase, spawns new executor config if needed).

**Comparison**:

| Aspect | 5-Turn Oversight | 30-Turn Replanning |
|--------|-----------------|-------------------|
| **Adaptation Speed** | Fast (detects issues in 5 turns) | Slow (may drift for 29 turns) |
| **Token Cost** | Higher (12 oversights per 60 turns) | Lower (2 replans per 60 turns) |
| **Per-Call Cost** | Cheaper (800 tokens, tools only) | Expensive (1200 tokens, full replan) |
| **Flexibility** | Per-phase tool subsetting | Fixed tools for 30 turns |
| **Error Correction** | Early detection (5-turn window) | Late detection (30-turn window) |

**Token Math** (60-turn mission):
- **5-turn oversight**: 12 tactician calls × 800 tokens = 9,600 tokens
- **30-turn replanning**: 2 strategist calls × 1200 tokens = 2,400 tokens
- **Difference**: 4× more tokens, but 6× faster adaptation

**Decision Justification**: 5-turn interval enables **rapid phase transitions** and **tool subsetting** (e.g., removing `report_completion` until verification phase). Critical for 2B model needing frequent guidance.

### Phase-Based Tool Subsetting

**Implementation**:
```python
state.current_tool_names = ["click_element", "press_key"]  # From tactician
filtered_tools = state.get_executor_tools()  # Filters TOOL_REGISTRY
```

**Rationale**:
1. **Token Efficiency**: Sending 2 tools (~200 lines JSON) vs. 9 tools (~900 lines) = 78% reduction
2. **Prevents Inappropriate Use**: No `report_completion` during execution phase (prevents premature completion)
3. **Simplifies Decision Space**: 2 tools = easier choice for 2B model than 9 tools
4. **Phase-Specific Constraints**: Reconnaissance phase = navigation only (no text input)

**Example Tool Subsets**:
- **Reconnaissance**: `["click_element", "scroll_down", "scroll_up"]` (3 tools)
- **Execution (Notepad)**: `["click_element", "type_text", "press_key"]` (3 tools)
- **Verification**: `["click_element", "report_completion"]` (2 tools)

**Trade-offs**:

| Aspect | Tool Subsetting | All Tools Always |
|--------|----------------|------------------|
| **Token Cost** | Low (200-400 lines) | High (900 lines) |
| **Flexibility** | Limited (tactician must manage) | High (executor decides) |
| **Error Prevention** | High (wrong tool unavailable) | Low (executor may misuse) |
| **Configuration Overhead** | High (tactician must update tools) | None (static toolset) |

**Decision Justification**: Critical for 2B model—reduces decision complexity and prevents errors (e.g., calling `drag_element` when dragging not needed).

### Vision-Augmented Strategist (vs. Text-Only)

**Implementation**:
```python
resp = post_json({
    "messages": [
        {"role": "system", "content": STRATEGIST_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": f"Mission: {task}"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        ]}
    ]
})
```

**Rationale**:
1. **Risk Assessment**: Visual evidence reveals UI-specific hazards (e.g., small buttons, dropdown auto-close)
2. **Phase Planning**: Initial screenshot informs reconnaissance needs (e.g., "calculator already open" vs. "desktop empty")
3. **Context Accuracy**: Mission "open calculator" interpreted differently if calculator already visible
4. **Operational Risks Section**: Strategist can cite specific UI elements (e.g., "Paint brush size 1px → invisible strokes")

**Example Risk Identification**:
- **Mission**: Draw star in Paint
- **Screenshot**: Shows Paint with 1px brush selected
- **Strategist Output**: "OPERATIONAL RISKS: Brush size 1px will produce invisible strokes. Must click brush size dropdown and select 5px+ before drawing."

**Trade-offs**:

| Aspect | Vision-Augmented | Text-Only |
|--------|-----------------|-----------|
| **Token Cost** | High (~5K image tokens) | Low (text only) |
| **Planning Accuracy** | High (context-aware) | Low (generic plans) |
| **Risk Detection** | Proactive (sees hazards) | Reactive (discovers during execution) |
| **Startup Time** | Slow (image processing) | Fast |

**Decision Justification**: Vision enables **proactive risk detection** (critical for 2B model lacking common-sense reasoning). Initial token cost (~5K) amortized over entire mission.

---

## 12. MODIFIABILITY ASSESSMENT

### Easy Extensions

**Adding Executor Tools**:
1. Define tool in `EXECUTOR_TOOLS` list:
   ```python
   {
       "type": "function",
       "function": {
           "name": "triple_click_element",
           "description": "Triple-click to select paragraph",
           "parameters": {...}
       }
   }
   ```
2. Update `TOOL_REGISTRY` (automatic if using list comprehension)
3. Add execution logic in `execute_tool_action()`:
   ```python
   elif name == "triple_click_element":
       # Implementation here
   ```
4. Tactician automatically gains access (can add to phase tools)

**Adjusting Oversight Interval**:
```python
TACTICIAN_INTERVAL = 3  # Change from 5 to 3
# No other code changes needed
```

**Custom Tactician Strategies**:
- Modify `TACTICIAN_PROMPT_TEMPLATE` (string replacement)
- Add decision criteria (e.g., "Transition to verification if result visible for 3 consecutive turns")
- No code changes (prompt-only modification)

**Per-Phase Timing**:
```python
PHASE_DELAYS = {
    "RECONNAISSANCE": 1.0,
    "EXECUTION": 2.5,
    "VERIFICATION": 0.5
}
time.sleep(PHASE_DELAYS.get(state.current_phase, TIMING_TURN_DELAY))
```

### Refactoring Opportunities

**Class Extraction** (improve modularity):

1. **`ScreenshotCapture` class**:
   ```python
   class ScreenshotCapture:
       def __init__(self, width, height):
           self.width = width
           self.height = height
       
       def capture(self) -> Tuple[bytes, int, int]:
           # capture_png logic here
   
       def save(self, png: bytes, turn: int) -> str:
           # save_screenshot logic here
   ```

2. **`InputController` class**:
   ```python
   class InputController:
       def __init__(self, screen_width, screen_height):
           self.sw = screen_width
           self.sh = screen_height
       
       def click(self, x_norm, y_norm, button="left"):
           # Normalized coordinate handling + click
       
       def type(self, text):
           # type_text logic
   ```

3. **`ToolExecutor` class**:
   ```python
   class ToolExecutor:
       def __init__(self, input_controller):
           self.controller = input_controller
       
       def execute(self, tool_name, args) -> str:
           # execute_tool_action logic here
   ```

**Benefits**: Clear separation of concerns, easier testing, reusable components.

**Externalize Persona Prompts**:
```python
# prompts/strategist.txt
You are a **General** (strategic command) for Windows desktop automation.
...

# Load at runtime
with open("prompts/strategist.txt") as f:
    STRATEGIST_PROMPT = f.read()
```

**Benefits**: Non-programmers can edit prompts, version control for prompt changes, A/B testing.

**Per-Application Timing Profiles**:
```python
TIMING_PROFILES = {
    "notepad.exe": {
        "ui_render": 0.5,
        "cursor_settle": 0.1
    },
    "chrome.exe": {
        "ui_render": 3.0,
        "cursor_settle": 0.15
    }
}

# Detect active app and use profile
active_app = get_active_window_exe()  # New function
timings = TIMING_PROFILES.get(active_app, DEFAULT_TIMINGS)
time.sleep(timings["ui_render"])
```

**Benefits**: Optimized delays per app (fast for Notepad, slow for browsers).

**Async API Calls** (performance optimization):
```python
import asyncio
import aiohttp

async def post_json_async(payload):
    async with aiohttp.ClientSession() as session:
        async with session.post(LMSTUDIO_ENDPOINT, json=payload) as resp:
            return await resp.json()

# Overlap API call with screenshot capture
api_task = asyncio.create_task(invoke_executor_async(state))
png, sw, sh = capture_png(512, 256)  # Runs concurrently
tool_call = await api_task
```

**Benefits**: Reduces turn time by ~1-2s (API call + screenshot overlap).

### Hard-Coded Values Requiring Config

**Tool Registry** (should support dynamic loading):
- Currently: `TOOL_REGISTRY` built from hardcoded `EXECUTOR_TOOLS` list
- Improvement: Load tools from `tools/*.json` directory
  ```python
  def load_tools(directory="tools"):
      tools = []
      for file in os.listdir(directory):
          with open(os.path.join(directory, file)) as f:
              tools.append(json.load(f))
      return {t["function"]["name"]: t for t in tools}
  
  TOOL_REGISTRY = load_tools()
  ```

**Timing Constants** (should support per-app overrides):
- Currently: Single global timing values (2.5s UI render for all apps)
- Improvement: Config file with per-app timing:
  ```json
  {
    "default": {"ui_render": 2.5, "cursor_settle": 0.12},
    "notepad.exe": {"ui_render": 0.5},
    "chrome.exe": {"ui_render": 4.0}
  }
  ```

**File Paths** (should be configurable):
- Hardcoded: `DUMP_DIR = "dumps"`, `DUMP_PREFIX = "screen_"`
- Improvement: Environment variables or config file:
  ```python
  DUMP_DIR = os.getenv("AGENT_DUMP_DIR", "dumps")
  DUMP_PREFIX = os.getenv("AGENT_DUMP_PREFIX", "screen_")
  ```

**LM Studio Endpoint** (should support multiple backends):
- Hardcoded: `LMSTUDIO_ENDPOINT = "http://localhost:1234/v1/chat/completions"`
- Improvement: Config file with provider selection:
  ```python
  PROVIDERS = {
      "lmstudio": "http://localhost:1234/v1/chat/completions",
      "openai": "https://api.openai.com/v1/chat/completions"
  }
  ENDPOINT = PROVIDERS[os.getenv("AGENT_PROVIDER", "lmstudio")]
  ```

**VK_MAP** (keyboard mapping hardcoded):
- Only 26 keys supported (no F5-F12, no numpad)
- Improvement: Load from `keyboard_mappings.json`:
  ```json
  {
    "enter": 13,
    "f5": 116,
    "numpad_0": 96
  }
  ```

**Screen Resolution** (hardcoded test resolution):
- `AGENT_IMAGE_W = 512`, `AGENT_IMAGE_H = 256`
- Improvement: Auto-detect optimal resolution based on screen aspect ratio:
  ```python
  def calculate_capture_size(target_width=1536):
      sw, sh = get_screen_size()
      aspect = sw / sh
      return (target_width, int(target_width / aspect))
  ```

---

# ISSUES.md

## FUNCTIONAL BUGS

### 1. Scroll Direction May Be Inverted
**Location**: `scroll_action()` function
**Issue**: Code uses `delta = 120` for `direction > 0` (scroll up) and `delta = -120` for `direction <= 0` (scroll down).
**Standard**: Windows `MOUSEEVENTF_WHEEL` convention is +120 = scroll UP (away from user), -120 = scroll DOWN (toward user).
**Impact**: `scroll_up` and `scroll_down` tools work correctly (pass `direction=1` and `direction=-1`).
**Status**: Code is CORRECT—no inversion bug. Tool names accurately describe behavior.

### 2. Tactician Fallback Only Triggers on Turn 1
**Location**: `run_agent()` main loop
**Code**:
```python
if executor_prompt and phase_name and tool_names:
    state.update_executor_context(...)
elif state.turn == 1:
    # Fallback only here
```
**Issue**: If tactician fails on turn 6, 11, etc. (oversight turns), no fallback logic—agent continues with stale configuration.
**Impact**: Executor may operate with wrong phase tools after failed tactician update.
**Fix**: Expand fallback to all oversight turns:
```python
if executor_prompt and phase_name and tool_names:
    state.update_executor_context(...)
elif not state.current_executor_prompt:  # No config at all
    # Trigger fallback
```

### 3. Screenshot Capture Has No Explicit Settle Delay
**Location**: `run_agent()` main loop
**Code**:
```python
time.sleep(TIMING_UI_RENDER)  # In execute_tool_action
png, sw, sh = capture_png(512, 256)  # Immediately after action
```
**Issue**: `TIMING_SCREENSHOT_SETTLE = 3.4s` defined but never used. Screenshot captures 2.5s after action (only `UI_RENDER` delay), not 3.4s.
**Impact**: Race condition—UI may not be fully rendered when screenshot taken (especially on slow systems).
**Fix**: Add explicit delay before capture:
```python
time.sleep(TIMING_SCREENSHOT_SETTLE - TIMING_UI_RENDER)  # 0.9s additional
png, sw, sh = capture_png(512, 256)
```

### 4. `get_executor_tools()` Silently Ignores Unknown Tool Names
**Location**: `AgentState.get_executor_tools()`
**Code**:
```python
return [TOOL_REGISTRY[name] for name in self.current_tool_names if name in TOOL_REGISTRY]
```
**Issue**: If tactician specifies `["click_element", "invalid_tool", "press_key"]`, only `["click_element", "press_key"]` returned—no warning logged.
**Impact**: Executor silently loses tools, mission may fail without explanation.
**Fix**: Log warnings for unknown tools:
```python
tools = []
for name in self.current_tool_names:
    if name in TOOL_REGISTRY:
        tools.append(TOOL_REGISTRY[name])
    else:
        print(f"⚠️ Unknown tool '{name}' ignored")
return tools
```

### 5. Double-Click Timing Too Fast
**Location**: `double_click()` function
**Code**: `time.sleep(TIMING_CLICK_DOUBLE)  # 0.05s = 50ms`
**Issue**: Windows double-click threshold is typically 200-500ms. 50ms may not be recognized as double-click by some apps.
**Impact**: Double-clicks may behave as two separate single clicks (e.g., opening file in new window instead of editing).
**Fix**: Increase to 100-150ms:
```python
TIMING_CLICK_DOUBLE = 0.1  # 100ms
```

### 6. Empty Tool List Not Validated
**Location**: `invoke_executor()`
**Code**:
```python
executor_tools = state.get_executor_tools()
if not executor_tools:
    print("⚠️ No tools available - using fallback")
    executor_tools = EXECUTOR_TOOLS  # All 9 tools
```
**Issue**: If tactician provides `tool_names=[]` (empty list), executor gets ALL tools as fallback (including `report_completion` inappropriately).
**Impact**: Premature completion possible during execution phase.
**Fix**: Distinguish empty list from None:
```python
if state.current_tool_names is None or not state.current_tool_names:
    # Use default safe toolset
    executor_tools = [TOOL_REGISTRY[n] for n in ["click_element", "press_key"]]
else:
    executor_tools = state.get_executor_tools()
```

### 7. GDI Resource Leak on Exception
**Location**: `capture_png()` function
**Issue**: If `StretchBlt` fails, function raises exception BEFORE cleanup:
```python
if not gdi32.StretchBlt(...):
    raise RuntimeError("StretchBlt failed")  # Leaks hdc_mem, hbm
```
**Impact**: Repeated failures leak GDI handles (limited to 10,000 per process) → eventual crash.
**Fix**: Use try/finally:
```python
try:
    if not gdi32.StretchBlt(...):
        raise RuntimeError("StretchBlt failed")
    # ... rest of logic
finally:
    gdi32.SelectObject(hdc_mem, old)
    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(None, hdc_scr)
```

---

## MAINTAINABILITY ISSUES

### 1. Magic Numbers Without Named Constants
**Examples**:
- `state.history[-8:]` (8 = arbitrary history send limit)
- `len(evidence.strip()) < 100` (100 = minimum evidence chars)
- `tool_calls[0]` (0 = single-action enforcement index)
- `"✓"`, `"⚠️"`, `"✗"` (Unicode symbols—no constants)

**Improvement**:
```python
MAX_HISTORY_SENT = 8
MIN_EVIDENCE_CHARS = 100
SINGLE_ACTION_INDEX = 0
SYMBOL_SUCCESS = "✓"
SYMBOL_WARNING = "⚠️"
SYMBOL_ERROR = "✗"
```

### 2. Hard-Coded File Paths
**Examples**:
- `DUMP_DIR = "dumps"`
- `DUMP_PREFIX = "screen_"`
- `os.path.join(DUMP_DIR, f"checkpoint_T{state.turn}.json")`

**Issues**:
- No support for custom output directories
- Risk of path conflicts (multiple agents running in same directory)
- No cleanup of old screenshots (directory grows unbounded)

**Improvement**:
```python
import tempfile
DUMP_DIR = os.getenv("AGENT_DUMP_DIR", tempfile.mkdtemp(prefix="agent_"))
```

### 3. Scattered Configuration
**Issue**: Config values spread across file (lines 1-50) instead of single object.

**Current**:
```python
LMSTUDIO_ENDPOINT = "..."
LMSTUDIO_MODEL = "..."
AGENT_IMAGE_W = 512
TACTICIAN_INTERVAL = 5
```

**Improvement**:
```python
class Config:
    # API Settings
    LMSTUDIO_ENDPOINT = "http://localhost:1234/v1/chat/completions"
    LMSTUDIO_MODEL = "qwen3-vl-2b-instruct"
    
    # Timing
    TIMING_CURSOR_SETTLE = 0.12
    TIMING_UI_RENDER = 2.5
    
    # Hierarchy
    TACTICIAN_INTERVAL = 5
    MAX_HISTORY_ITEMS = 10

config = Config()
```

### 4. Missing Docstrings/Comments
**Examples**:
- `norm_to_px()`: No explanation of 0-1000 scale or clamping logic
- `draw_cursor()`: No comment on why hotspot adjustment needed
- `prune_history()`: No rationale for FIFO strategy (why not priority-based?)

**Improvement**: Add docstrings to all functions:
```python
def norm_to_px(xn: float, yn: float, sw: int, sh: int) -> Tuple[int, int]:
    """
    Convert normalized coordinates (0-1000 scale) to physical pixels.
    
    Args:
        xn: X coordinate (0=left, 1000=right)
        yn: Y coordinate (0=top, 1000=bottom)
        sw: Screen width in pixels
        sh: Screen height in pixels
    
    Returns:
        (px, py) tuple clamped to [0, sw-1] × [0, sh-1]
    
    Precision: ±0.5 pixel rounding error
    """
```

### 5. Inconsistent Error Handling
**Issue**: Some functions raise exceptions, others return None/error strings—no consistent pattern.

**Examples**:
- `post_json()`: Raises exception
- `invoke_strategist()`: Returns error string
- `invoke_tactician()`: Returns (None, None, None)
- `execute_tool_action()`: Returns "Error: ..." string

**Improvement**: Define error handling strategy:
```python
class AgentError(Exception):
    """Base exception for agent errors"""
    pass

class APIError(AgentError):
    """LLM API call failed"""
    pass

class ToolExecutionError(AgentError):
    """Tool execution failed"""
    pass
```

### 6. Prompt Text Embedded in Code
**Issue**: 3 large prompt strings (419, 300, 123 words) hardcoded in Python file—difficult to edit, version, and A/B test.

**Improvement**:
```
project/
├── agent.py
├── prompts/
│   ├── strategist.txt
│   ├── tactician.txt
│   └── executor_fallback.txt
└── tools/
    ├── click_element.json
    └── report_completion.json
```

---

## PERFORMANCE CONCERNS

### 1. Fixed 3.5s Turn Delay Wastes Time
**Issue**: `time.sleep(TIMING_TURN_DELAY)` at end of every turn, regardless of action complexity.

**Examples**:
- Pressing "enter" key: 0.1s execution + 3.5s delay = 3.6s wasted
- Scrolling: 0.5s execution + 3.5s delay = 3.0s wasted

**Impact**: Simple 20-action mission takes 20 × 3.5s = 70s of pure delay time.

**Improvement**: Adaptive delays per action type:
```python
ACTION_DELAYS = {
    "press_key": 0.5,
    "scroll_down": 0.5,
    "scroll_up": 0.5,
    "click_element": 1.0,
    "type_text": lambda text: 0.5 + len(text) * 0.01,
    "drag_element": 2.0
}
delay = ACTION_DELAYS.get(tool_name, 3.5)
if callable(delay):
    delay = delay(tool_args.get("text", ""))
time.sleep(delay)
```

### 2. Redundant Base64 Encoding
**Issue**: Screenshot base64-encoded every turn (even if unchanged between oversight turns).

**Current**:
```python
# Turn 2-5: Same screenshot sent 4 times
b64 = base64.b64encode(state.screenshot).decode("ascii")
```

**Improvement**: Cache encoding:
```python
class AgentState:
    def __init__(self, ...):
        self._screenshot_b64_cache = None
    
    def update_screenshot(self, png):
        self.screenshot = png
        self._screenshot_b64_cache = base64.b64encode(png).decode("ascii")
    
    def get_screenshot_b64(self):
        return self._screenshot_b64_cache
```

**Savings**: ~50ms per turn (for 100KB PNG).

### 3. History Rebuilt Every Turn
**Issue**: `build_history_text()` iterates history, formats strings, and concatenates—repeated work.

**Optimization**: Incremental history updates:
```python
class AgentState:
    def __init__(self, ...):
        self._history_text_cache = ""
    
    def add_history(self, ...):
        entry = {...}
        self.history.append(entry)
        
        # Append to cache
        target = entry['args'].get('label', '')[:30]
        self._history_text_cache += f"\n  T{entry['turn']}: {entry['tool']}({target}) → {entry['result'][:60]}"
    
    def build_history_text(self):
        # Return cached version
        return f"MISSION: {self.task}\n...\n{self._history_text_cache}"
```

### 4. Inefficient Coordinate Transformation
**Issue**: `norm_to_px()` called twice per click (x and y separately in some contexts).

**Current** (hypothetical inefficiency):
```python
px = norm_to_px(position[0], 0, sw, sh)[0]
py = norm_to_px(0, position[1], sw, sh)[1]
```

**Actual Code**: Calls once per coordinate pair (no issue). But function does 4 operations (clamp, scale, round, clamp) when 2 suffice.

**Optimization**:
```python
def norm_to_px(xn: float, yn: float, sw: int, sh: int) -> Tuple[int, int]:
    # Single clamped scale+round
    px = int((max(0, min(1000, xn)) / 1000.0) * sw + 0.5)
    py = int((max(0, min(1000, yn)) / 1000.0) * sh + 0.5)
    return (min(px, sw - 1), min(py, sh - 1))
```

**Savings**: ~10% faster (negligible impact).

---

## SECURITY/SAFETY GAPS

### 1. Unrestricted System Access
**Issue**: No forbidden key combinations—agent can press:
- `"windows+l"` (lock screen → abort mission)
- `"alt+f4"` (close active window → may close agent's own terminal)
- `"ctrl+alt+delete"` (security screen → freezes automation)

**Impact**: Agent may lock user out, close critical apps, trigger security prompts.

**Mitigation**:
```python
FORBIDDEN_KEYS = ["windows+l", "ctrl+alt+delete", "alt+f4"]

def press_key(key):
    if key.lower() in FORBIDDEN_KEYS:
        raise SecurityError(f"Forbidden key combo: {key}")
```

### 2. No Input Validation (Text Length)
**Issue**: `type_text()` accepts unlimited text—agent could type 10,000-character string.

**Impact**:
- May crash target app (buffer overflow in ancient apps)
- Slows execution (10K chars × 5ms = 50s typing time)
- Fills logs with noise

**Mitigation**:
```python
MAX_TEXT_LENGTH = 1000

def type_text(text: str):
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Text too long: {len(text)} > {MAX_TEXT_LENGTH}")
```

### 3. No Coordinate Bounds Validation (User Input)
**Issue**: `norm_to_px()` clamps out-of-range values, but no warning—LLM never learns coordinates were invalid.

**Example**: LLM outputs `[1500, -200]` → clamped to `[1000, 0]` → clicks wrong location → LLM thinks coordinates were correct.

**Impact**: Agent repeats invalid coordinates (no error feedback).

**Mitigation**:
```python
def norm_to_px(xn: float, yn: float, sw: int, sh: int) -> Tuple[int, int]:
    if not (0 <= xn <= 1000 and 0 <= yn <= 1000):
        raise ValueError(f"Coordinates out of range: [{xn}, {yn}] (expected 0-1000)")
```

### 4. No Disk Space Checks
**Issue**: Screenshot saving (`save_screenshot()`) never checks available disk space—may fill drive.

**Impact**:
- 600 turns × 100KB/screenshot = 60MB (acceptable)
- But full archive + checkpoints may grow to GB scale
- No cleanup of old screenshots

**Mitigation**:
```python
import shutil

def save_screenshot(png, turn):
    free_space = shutil.disk_usage(DUMP_DIR).free
    if free_space < 100 * 1024 * 1024:  # 100MB minimum
        raise IOError(f"Low disk space: {free_space / 1024 / 1024:.1f}MB")
    # ... rest of save logic
```

### 5. No Rate Limiting
**Issue**: If `TIMING_TURN_DELAY` set to 0, agent could make 100s of API calls/second → overwhelm LM Studio.

**Impact**: LM Studio OOM crash, system freeze, network saturation.

**Mitigation**:
```python
MIN_TURN_DELAY = 1.0  # Absolute minimum (safety floor)

# In main loop
time.sleep(max(TIMING_TURN_DELAY, MIN_TURN_DELAY))
```

### 6. No Authentication for LM Studio API
**Issue**: `LMSTUDIO_ENDPOINT` is http://localhost:1234—no authentication.

**Risk**: If LM Studio exposed on network (0.0.0.0 binding), anyone on LAN can use API.

**Mitigation**: Use API keys:
```python
LMSTUDIO_API_KEY = os.getenv("LMSTUDIO_API_KEY")
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LMSTUDIO_API_KEY}"
}
```

---

## ARCHITECTURE WEAKNESSES

### 1. Tactician Tool Call Failures Not Logged
**Issue**: `invoke_tactician()` catches exceptions and returns `(None, None, None)` silently—no detailed logging.

**Code**:
```python
except Exception as e:
    print(f"Tactician call failed: {e}")  # Only prints exception message
    return (None, None, None)
```

**Impact**: If tactician fails due to malformed JSON, timeout, or API error, no diagnostic info—hard to debug.

**Improvement**:
```python
import traceback

except Exception as e:
    print(f"⚠️ Tactician call failed: {e}")
    traceback.print_exc()  # Full stack trace
    # Log to file
    with open(os.path.join(DUMP_DIR, f"tactician_error_T{state.turn}.log"), "w") as f:
        f.write(traceback.format_exc())
    return (None, None, None)
```

### 2. No Verification of Tool Subsetting Correctness
**Issue**: No validation that tactician's `tool_names` actually makes sense for phase.

**Example**: Tactician spawns "VERIFICATION" phase but provides `tool_names=["click_element", "scroll_down"]` (missing `report_completion`).

**Impact**: Executor cannot complete mission (tool not available).

**Improvement**: Phase-tool compatibility matrix:
```python
REQUIRED_TOOLS_PER_PHASE = {
    "VERIFICATION": ["report_completion"],  # Must include
    "EXECUTION": ["click_element", "type_text"]  # At least one of
}

def validate_phase_tools(phase, tool_names):
    required = REQUIRED_TOOLS_PER_PHASE.get(phase, [])
    missing = [t for t in required if t not in tool_names]
    if missing:
        print(f"⚠️ Phase '{phase}' missing required tools: {missing}")
```

### 3. Fallback Logic Only on Turn 1 (Architectural Constraint)
**Issue**: After turn 1, no fallback if tactician fails—agent may continue indefinitely with stale config.

**Scenario**:
- Turn 6: Tactician oversight fails (API timeout)
- Turns 7-11: Executor operates with turn 1 configuration (wrong phase)
- Turn 11: Tactician finally succeeds, corrects phase
- Result: 5 wasted turns

**Improvement**: Add "staleness detector":
```python
# In AgentState
self.last_tactician_success = 0

# In run_agent()
if state.turn - state.last_tactician_success > 15:
    print("⚠️ Tactician offline for 15 turns—triggering emergency fallback")
    state.update_executor_context(EXECUTOR_FALLBACK_PROMPT, "EMERGENCY", DEFAULT_TOOLS)
```

### 4. No History Prioritization
**Issue**: Simple FIFO pruning—all actions treated equally.

**Problem**: Critical events (phase transitions, errors) dropped from history after 10 turns.

**Example**:
- Turn 5: Phase transition to EXECUTION
- Turns 6-15: 10 actions
- Turn 16: History no longer contains phase transition context

**Improvement**: Priority tiers:
```python
def prune_history(history, max_items):
    # Keep all phase transitions + errors
    critical = [h for h in history if h["tool"] == "spawn_executor_prompt" or h["result"].startswith("Error")]
    recent = [h for h in history if h not in critical][-max_items:]
    return sorted(critical + recent, key=lambda h: h["turn"])
```

### 5. No Mission Timeout
**Issue**: Agent runs for `MAX_STEPS=600` turns regardless of progress—may loop for hours.

**Impact**: Wasted compute, no early abort on unachievable missions.

**Improvement**:
```python
MISSION_TIMEOUT = 30 * 60  # 30 minutes
start_time = time.time()

# In main loop
if time.time() - start_time > MISSION_TIMEOUT:
    return f"Mission timeout after {MISSION_TIMEOUT}s"
```

### 6. No Success Criteria Validation
**Issue**: `report_completion` accepted solely based on evidence length (100 chars)—no actual success verification.

**Problem**: Agent may report completion prematurely:
- Evidence: "Calculator open showing result 8 (correct answer to 5+3). Clear display, no errors, mission accomplished. Ready to proceed."
- Reality: Calculator shows "7" (wrong answer)

**Improvement**: Ask strategist to define success criteria, validate in verification phase:
```python
# In STRATEGIST_PROMPT
"6. SUCCESS CRITERIA: List 3-5 visual indicators of completion (e.g., 'Calculator displays 8', 'Save dialog closed')"

# In report_completion handling
if not validate_success_criteria(evidence, state.strategist_doctrine):
    print("✗ Evidence does not match success criteria")
    return "Continue mission"
```

---

**END OF DOCUMENTATION**