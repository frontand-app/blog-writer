# Blog Article Writer

An AI-powered blog article generation system that creates SEO-optimized, long-form blog posts using Google's Gemini models. The system integrates URL validation, research capabilities, and comprehensive quality assurance to ensure **110% quality output ALWAYS**.

## Features

- **Structured Content Generation**: Creates blog articles with headlines, sections, FAQs, PAA, and sources
- **URL Validation**: Automatically validates and filters sources using Gemini with Google Search grounding
- **Research Capabilities**: Deep research report generation for comprehensive topics
- **SEO Optimization**: Generates meta titles, descriptions, and keyword-optimized content
- **Multi-language Support**: Supports multiple languages (en, de, fr, es, pt, etc.)
- **Quality Assurance**: Comprehensive quality checks ensure 110% quality output
- **Modal Deployment Ready**: Pre-configured for deployment on Modal

## Quality Guarantee

Every article passes:
- ✅ **12+ Critical Quality Checks** (blocking errors)
- ✅ **15+ Warning Checks** (non-blocking)
- ✅ **100% URL Validation** (all sources checked)
- ✅ **100% HTML Validation** (well-formed HTML guaranteed)
- ✅ **Automatic Fixes** (meta tags, citations, HTML)

See [QUALITY_ASSURANCE.md](QUALITY_ASSURANCE.md) for details.

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd blog-writer
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

## Configuration

### Environment Variables

- `GOOGLE_API_KEY`: Google AI API key (required)
- `GEMINI_API_KEY`: Alternative API key (falls back to GOOGLE_API_KEY)
- `GOOGLE_GENAI_USE_VERTEXAI`: Set to "true" to use Vertex AI (optional)
- `GOOGLE_CLOUD_PROJECT`: Google Cloud project ID (required if using Vertex AI)
- `GOOGLE_CLOUD_LOCATION`: Google Cloud location (default: "global")
- `OUTPUT_DIR`: Output directory for generated files (default: "output")

### Vertex AI Setup (Alternative)

If using Vertex AI instead of Google AI API:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=global
gcloud auth application-default login
```

## Usage

### CLI Usage

Generate a blog article from a JSON input file:

```bash
python -m src.main --input input.json --output output.json
```

Generate HTML output:

```bash
python -m src.main --input input.json --output article.html --format html
```

### Input Schema

Create an input JSON file with the following structure:

```json
{
  "primary_keyword": "AI adoption in customer service",
  "company_url": "https://example.com",
  "company_name": "Example Corp",
  "company_language": "en",
  "company_location": "Germany",
  "company_competitors": ["competitor1.com", "competitor2.io"],
  "company_info": {
    "industry": "SaaS",
    "focus": "Customer experience"
  },
  "content_generation_instruction": "Focus on B2B use cases",
  "links": ["/product", "/features"],
  "scope": "EU focus; B2C and B2B; service interactions"
}
```

### Output Schema

The generator produces a structured output with:

- Headline, subtitle, teaser, intro
- Meta title and description
- Up to 9 sections with titles and content
- Key takeaways (up to 3)
- FAQ items (up to 6)
- PAA items (up to 4)
- Sources (up to 20 validated URLs)
- Search queries used
- Read time estimate
- Publication date
- Formatted literature/references
- Full HTML output

### Python API Usage

```python
from src.config import Config
from src.generators.content_generator import ContentGenerator
from src.schemas.input import InputSchema

# Create input schema
input_data = InputSchema(
    primary_keyword="AI adoption in customer service",
    company_url="https://example.com",
    company_name="Example Corp",
    company_language="en",
    company_location="Germany",
    company_competitors=["competitor1.com"],
    company_info={"industry": "SaaS"},
    content_generation_instruction="Focus on B2B",
    links=["/product"],
)

# Generate content
config = Config()
generator = ContentGenerator(config=config)
output = generator.generate(input_data)

# Access output fields
print(output.headline)
print(output.sections)
print(output.html)
```

### URL Validation Agent

Use the validator agent independently:

```python
from src.agents.validator import ValidatorAgent

agent = ValidatorAgent()
results = agent.validate_urls(
    query="AI adoption in European CX",
    company_url="https://example.com",
    competitors=["competitor.com"],
    language="en",
    max_results=3,
)
```

### Research Agent

Generate deep research reports:

```python
from src.agents.research import ResearchAgent

agent = ResearchAgent()
report = agent.generate_research_report(
    topic="Trust dynamics in AI-powered customer service",
    scope="EU focus; B2C and B2B; service interactions",
)
```

## Modal Deployment

### Setup

1. Install Modal CLI:
```bash
pip install modal
```

2. Authenticate:
```bash
modal token new
```

3. Set up secrets:
```bash
modal secret create google-api-key GOOGLE_API_KEY=your-api-key
```

### Deploy

```bash
modal deploy modal/app.py
```

### Usage

The deployed endpoints:

- `POST /generate_blog_article`: Generate a blog article
- `validate_urls`: Validate URLs (function call)
- `generate_research_report`: Generate research report (function call)

Example API call:

```bash
curl -X POST https://your-app.modal.run/generate_blog_article \
  -H "Content-Type: application/json" \
  -d @input.json
```

## Project Structure

```
blog-writer/
├── src/
│   ├── __init__.py
│   ├── main.py                 # CLI entry point
│   ├── config.py               # Configuration management
│   ├── schemas/
│   │   ├── input.py           # Input schema definitions
│   │   └── output.py          # Output schema definitions
│   ├── agents/
│   │   ├── validator.py       # URL validation agent
│   │   └── research.py        # Research report agent
│   ├── generators/
│   │   ├── content_generator.py  # Main content generator
│   │   └── post_processor.py     # Post-processing utilities
│   └── utils/
│       └── helpers.py         # Utility functions
├── modal/
│   └── app.py                  # Modal deployment
├── tests/                      # Test files
├── requirements.txt            # Python dependencies
├── .env.example               # Environment template
└── README.md                   # This file
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

This project follows PEP 8 style guidelines. Consider using `black` for formatting:

```bash
pip install black
black src/
```

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

## Support

[Add support information here]

