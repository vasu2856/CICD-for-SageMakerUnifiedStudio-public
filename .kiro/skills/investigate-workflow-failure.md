# Investigate GitHub Actions Workflow Failure

Use this skill when a GitHub Actions workflow run has failed and you need to diagnose the root cause.

## Step 1: Get the High-Level Failure Summary

```bash
gh run view <RUN_ID> --log 2>&1 | grep -E "ERROR|error|failed|Failed|Exception|❌|exit code 1" | grep -v "XCom\|heartbeat\|Node.js" | head -30
```

**If the error is clear from this output** (e.g. a missing secret, a permission error, a CLI failure with a descriptive message), you're done — report the root cause directly.

**If the error contains `AlgorithmError: [SM-111] Error with executing notebook`**, the failure is inside a SageMaker notebook execution. Proceed to Step 2.

---

## Step 2 (Notebook failures only): Identify the Execution ID and Parameters

From the error output, find a line like:
```
Execution <name>-<UUID> failed with error: AlgorithmError: [SM-111] Error with executing notebook
...
Params: {'param1': 'value1', ...}
```

Note:
- The **UUID** (e.g. `ae7e2a39-2b1c-4b97-85b6-c41936f37a6e`) — this is the SageMaker execution ID
- The **Params** — what papermill injected. Compare against the workflow yaml `input_params` to spot obvious mismatches (e.g. `None` values, truncated ARNs, wrong region)

If the params look wrong, you may already have the root cause without needing to fetch the notebook.

---

## Step 3 (Notebook failures only): Find the Notebook Output in S3

Search for the execution UUID across S3:

```bash
aws s3 ls s3://<BUCKET>/ --recursive 2>&1 | grep "<EXECUTION_UUID>" | sort | tail -3
```

To find the right bucket first:
```bash
aws s3 ls 2>&1 | grep -i "sagemaker\|smus"
```

Common path pattern:
```
shared/workflows/output/<app>/bundle/<workflow-type>/<execution-id>/output/output.tar.gz
```

---

## Step 4 (Notebook failures only): Download and Extract

```bash
aws s3 cp s3://<BUCKET>/<PATH>/output.tar.gz /tmp/notebook-output.tar.gz
tar -xzf /tmp/notebook-output.tar.gz -C /tmp/
```

The tar typically contains:
- `_<notebook_name>.ipynb` — the executed output notebook
- `sagemaker_job_execution.log` — the shell-level execution log

Check the execution log first for a quick summary:
```bash
cat /tmp/sagemaker_job_execution.log | tail -30
```

---

## Step 5 (Notebook failures only): Parse the Output Notebook for Errors

```python
import json, re
from html.parser import HTMLParser

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, data):
        self.text.append(data)
    def get_text(self):
        return ''.join(self.text)

with open('/tmp/_<notebook_name>.ipynb') as f:
    nb = json.load(f)

for i, cell in enumerate(nb['cells']):
    for out in cell.get('outputs', []):
        ot = out.get('output_type')
        if ot == 'error':
            print(f'Cell {i+1} ERROR: {out.get("ename")}: {out.get("evalue")[:300]}')
        elif ot == 'display_data':
            html = ''.join(out.get('data', {}).get('text/html', []))
            if 'Traceback' in html or 'Error' in html:
                p = HTMLTextExtractor()
                p.feed(html)
                print(f'Cell {i+1}:')
                print(p.get_text()[:1500])
```

To also verify what parameters were actually injected by papermill:
```python
for i, cell in enumerate(nb['cells']):
    tags = cell.get('metadata', {}).get('tags', [])
    if 'parameters' in tags or 'injected-parameters' in tags:
        print(f'Cell {i+1} ({tags}):')
        src = cell['source'] if isinstance(cell['source'], str) else ''.join(cell['source'])
        print(src)
```

---

## Common Root Causes

| Symptom | Root Cause | Fix |
|---|---|---|
| `ValueError: Must setup local AWS configuration with a region` | `sagemaker.Session()` called without `boto_session` | Pass `boto_session=boto3.Session(region_name=region)` |
| `NoRegionError: You must specify a region` | boto3 clients created at module import time without region | Set `os.environ['AWS_DEFAULT_REGION'] = region` before importing the module |
| Param `region` is `None` | `{domain.region}` not in workflow yaml `input_params` | Add `region: "{domain.region}"` to the workflow yaml and a `region = None` parameters cell to the notebook |
| ARN ends with `/` (no resource name) | DataZone connection stored a bad ARN; old boto3 couldn't deserialize the field | Upgrade boto3 >= 1.40.70; manually fix via `update_connection` |
| `ValidationException: The provided model identifier is invalid` | Bedrock model ID is legacy/deprecated | Check active models: `aws bedrock list-foundation-models --query 'modelSummaries[?modelLifecycle.status==\`ACTIVE\`].modelId'` |
| `ServiceQuotaExceededException` on workflow update | Workflow version quota hit | Run housekeeping script or delete old workflow versions |
| `AlgorithmError` at cell 1-2 | Region is `None`, causing cascade failures | See region fix above |
