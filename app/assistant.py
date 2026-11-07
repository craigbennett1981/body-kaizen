"""Setting up an AI assistant: the prompt the dashboard offers to copy after first-run setup (and from Profile).
It tells the assistant where the data folder is, what to read, how to recompute, and to write the person's CLAUDE.md
from the template in docs/CLAUDE.example.md, asking them to fill in the parts only they know."""
import data

REPO = "https://github.com/craigbennett1981/body-kaizen"

TEMPLATE = """# Food and fitness log: instructions for the assistant

## Start here
- Data: this folder ({data}). The Body Kaizen code is {code}.
- Before your first log in a session, read {guide} (how to log, every kind of input, rules) and {schema} (file
  format). Then read settings.yaml and targets.yaml here.
- After every change, recompute: {compute}. Commit in this folder if it's a git repository (YYYY-MM-DD: what changed).
- Show weights and distances in {units}. Files always stay metric; macros are always grams.
- Anything below overrides the guide.

## About me
- <Training: e.g. gym Mon/Wed/Fri evenings, an easy run at the weekend>
- <Habits: e.g. tea is always English breakfast with low-fat milk; I weigh most food cooked>
- <Goal: e.g. lose fat slowly while keeping strength>

## How I want it
- Tone: <direct; push back when I'm off track>.
- Ask what training I'm doing today if I haven't said.
"""


def build():
    B = data.bkenv
    clone = (B.CODE / "AI-GUIDE.md").exists()   # a clone has the guides beside the code; an install reads them online
    guide = str(B.CODE / "AI-GUIDE.md") if clone else f"{REPO}/blob/main/AI-GUIDE.md"
    schema = str(B.CODE / "SCHEMA.md") if clone else f"{REPO}/blob/main/SCHEMA.md"
    compute = (f"cd {B.CODE} && FT_DATA={B.DATA} python scripts/compute.py <date>" if (B.CODE / "pyproject.toml").exists()
               else "body-kaizen compute <date>")
    units = "pounds, miles, ounces and fluid ounces (imperial)" if B.units() == "imperial" else "kilograms, kilometres, grams and millilitres (metric)"
    claude_md = TEMPLATE.format(data=B.DATA, code=B.CODE, guide=guide, schema=schema, compute=compute, units=units)
    prompt = (f"Please set yourself up as my Body Kaizen assistant. Body Kaizen is my private health dashboard: I tell you what I "
              f"eat and how I train, and you log it in my data folder.\n\n"
              f"1. My data folder is {B.DATA}. Read {guide} and {schema} first.\n"
              f"2. Save the file below as CLAUDE.md in my data folder (if there's one already, show me the differences instead).\n"
              f"3. Then ask me, a few at a time, for the parts in <angle brackets>: my training, habits, goal and how I'd like "
              f"you to coach me. Fill them in and save.\n"
              f"4. Finish by asking what I've eaten so far today, and log it.\n\n"
              f"--- CLAUDE.md ---\n{claude_md}")
    return {"prompt": prompt, "claude_md": claude_md, "data_dir": str(B.DATA), "docs": f"{REPO}/blob/main/docs/logging-with-claude.md"}
