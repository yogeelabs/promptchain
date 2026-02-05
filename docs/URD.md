# User Requirements Document (URD)

## 5. Core User Capabilities (Must-Have)

### 5.0 Sequential Prompt Chains (Single → Many Steps)

- Users can run single prompts to get immediate results for straightforward tasks.
- Users can create sequential chains where the output of one prompt feeds into the next, enabling more complex, step-by-step processes.
- This allows users to build workflows that grow in complexity as needed, starting from simple to multi-step sequences.

### 5.1 Multi-Step Workflows

- Users can define workflows that consist of multiple steps, each representing a prompt or action.
- Each step may depend on the outputs or results of earlier steps in the chain.
- Users can run the entire workflow in one go or execute it step-by-step, reviewing results along the way.

### 5.2 Variable Substitution and Parameterization

- Users can insert variables into prompts to customize them dynamically.
- Parameters can be reused across steps to maintain consistency and flexibility.

### 5.3 Looping and Fan-Out

- Users can set up loops to repeat prompts over lists or collections.
- This enables processing multiple items or generating multiple outputs from one workflow.

### 5.4 Conditional Branching

- Users can include conditional logic to change the workflow path based on previous results.
- This allows workflows to adapt to different scenarios automatically.

### 5.5 Deterministic Re-Runs

- Users can reliably re-run workflows to get consistent results.
- This supports debugging and iterative refinement.

### 5.6 Flexible Inputs Per Step

- Each step in a workflow can accept different types of inputs, such as topics, files, or lists.
- Users can attach inputs to a specific step without changing earlier or later steps.
- Each step can take parameters, a text file, or a JSON file depending on the need.
- This flexibility enables users to tailor each step’s input according to the task.
- List inputs can be used to fan out a step, running it multiple times with different data.
- Users can provide their own list file when the pipeline does not produce the exact list they want.
- Prompts should stay simple and natural, without requiring internal schema language.

### 5.6.1 Per-Step File Inputs (User Stories)

- “I can attach a file to Stage 3 without changing Stage 1 or Stage 2.”
- “If my pipeline can’t produce the exact list I want, I can provide a file myself.”

### 5.6.2 Fan-Out From Plain Text Lists (User Stories)

- “I can write 5 items in a text file and fan out over them.”
- “Each line becomes a separate run with its own output.”

### 5.7 Use Different Models Per Step

- Users can select different AI models for different steps within a workflow.
- This allows leveraging the strengths of various models for specific tasks.
- Users can optionally set a per-step reasoning level (effort/verbosity of reasoning) when supported.

### 5.8 Review / Process Outputs Before Continuing

- After each step, users can review, edit, or apply filters to the output before moving on.
- This ensures quality control and allows adjustments mid-workflow.

### 5.9 Optional External Models

- Users can choose to use an external model provider if they want.
- External usage must be explicit and controllable.
- The tool must still work fully without external providers.
- OpenAI is optional and never required.

## 6. Execution Experience

### 6.1 Intuitive Run Controls

- Users can easily start, pause, or stop workflows.
- Clear feedback is provided during execution.

### 6.2 Progress Tracking and Logs

- Users can see which steps have completed and view detailed logs.
- This helps in understanding workflow behavior and troubleshooting.
- Logs and metadata show which provider, model, and reasoning level were used per step.

### 6.3 Final Outputs in a Dedicated Output Location

- Users want their final deliverables separated from intermediate files and artifacts.
- Final outputs are organized in a clear, easy-to-find location for convenience and clarity.
- Supporting/debug files live outside `output/` so deliverables stay clean.

### 6.4 External Provider Transparency

- Users can see which provider and model was used.
- Users can tell when external connectivity is required.
- Failures clearly indicate why they happened (network, auth, or rate limits).
- Failures do not erase prior outputs or logs.

### 6.5 Batch Execution Mode (Optional)

- Users can run a pipeline in interactive mode (default) or batch mode.
- Users can choose batch mode when processing large lists (e.g., hundreds of items).
- Users can submit a batch run and return later to collect results.
- Users can view clear batch status (submitted, running, completed, failed items).
- Users can retry only failed or missing items without restarting the full run.
- Final outputs remain easy to locate and separate from intermediate/support artifacts.
- Users can always see which execution mode was used for a run.

## 7. Non-Requirements

- PromptChain does not manage billing or optimize external model costs in the MVP; those are user-managed.
