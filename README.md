# Resume Optimizer (CV Tailor)

A small Streamlit app that tailors an existing resume to a specific job description using an LLM via [OpenRouter](https://openrouter.ai), then exports the result as a Word document and PDF.

The tailoring is deliberately conservative: it may reword, reorder and emphasise what is already in your resume (and use the job description's keywords where you genuinely have the experience), but it is instructed **never to invent or inflate** experience, skills, education or credentials.

## How it works

1. **Resume** – upload your current resume as a `.docx`. The text is extracted from paragraphs and tables.
2. **Job description** – paste the posting text (or upload a `.md`/`.txt` file).
3. **Generate** – choose a model and send both to OpenRouter. The model returns a structured JSON CV (name, contact, summary, skills, experience, education, certifications, extra sections).
4. **Results** – preview the tailored CV in the app, download the **DOCX** and **PDF**, or give feedback (e.g. *"make the summary shorter"*) and have the model revise it.

If a model returns malformed JSON, a cheap repair model cleans it up so the tailoring work isn't thrown away.

## Requirements

- Python 3.10+
- An [OpenRouter API key](https://openrouter.ai/keys)
- **PDF export only:** Windows or macOS with **Microsoft Word** installed. PDFs are produced by converting the DOCX through Word (`docx2pdf`). Without Word the DOCX is still generated and the app simply reports the PDF as unavailable.

## Setup

```bash
git clone https://github.com/sonnyanicetojr/resume-optimizer.git
cd resume-optimizer

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env        # Windows: copy .env.example .env
# then edit .env and set OPENROUTER_API_KEY
```

## Run

```bash
streamlit run app.py
```

The API key can also be pasted into the app's **Review & generate** step instead of using `.env`.

## Choosing a model

The model dropdown lists OpenRouter models grouped by vendor (OpenAI, Google, Anthropic, xAI, Meta, Mistral, DeepSeek, Qwen, Z-AI, Moonshot, and others), plus **Fusion**, which runs a panel of models and has a judge model merge the results.

- The list is hard-coded in `app.py` (`model_options`) and was verified against OpenRouter's catalogue on 2026-10-15. Models are added and retired often; the live list is at <https://openrouter.ai/api/v1/models>.
- Cost varies enormously between models, and every request asks for high reasoning effort, so check pricing before picking a top-tier model.
- Requests for Gemini models are restricted to the **Google AI Studio** provider (`llm_tailor.py`), so that provider must be usable from your OpenRouter account.

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | Streamlit UI: the 4-step flow, theme/CSS, model list |
| `llm_tailor.py` | OpenRouter client, Fusion plugin config, JSON extraction and repair |
| `prompts.py` | System prompt and user prompt template (the anti-fabrication rules live here) |
| `resume_parser.py` | Extracts text (and font info) from the source `.docx` |
| `cv_generator.py` | Builds the DOCX from the structured CV and converts it to PDF |
| `output/` | Generated CVs (git-ignored) |
| `.streamlit/config.toml` | Base Streamlit theme |

## Privacy

Your resume text and the job description are sent to OpenRouter and on to the model provider you select. Nothing is stored server-side by this app. `.env` and generated output are listed in `.gitignore` and are not committed.

## Notes

- Always read the tailored CV before sending it. The model is told not to fabricate, but you are responsible for what you submit.

## License

[MIT](LICENSE)
