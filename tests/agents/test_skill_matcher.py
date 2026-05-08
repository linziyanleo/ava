from ava.agents.nanobot.skill_matcher import (
    match_skill_for_message,
    natural_language_skill_matching,
    skill_match_narration,
)


SKILLS = [
    {
        "name": "llm-wiki",
        "description": "Save links, articles, notes, papers, transcripts and Markdown knowledge base entries.",
        "trigger_keywords": ["save article", "knowledge base", "wiki", "markdown note"],
    },
    {
        "name": "imagegen",
        "description": "Generate and edit raster images, product mockups, photos, illustrations and sprites.",
        "trigger_keywords": ["generate image", "edit image", "mockup", "sprite"],
    },
    {
        "name": "project-learner",
        "description": "Teach codebase structure and keep an interactive project learning log.",
        "trigger_keywords": ["learn project", "explain codebase", "study module"],
    },
    {
        "name": "playwright",
        "description": "Automate browser flows, click pages, fill forms and take screenshots.",
        "trigger_keywords": ["browser test", "click page", "screenshot", "form fill"],
    },
    {
        "name": "pdf",
        "description": "Read, split, merge, rotate, watermark and extract text from PDF files.",
        "trigger_keywords": ["pdf", "extract table", "merge pdf", "split pdf"],
    },
    {
        "name": "spreadsheets",
        "description": "Create, analyze and format spreadsheets, csv and xlsx files with charts.",
        "trigger_keywords": ["spreadsheet", "xlsx", "csv", "chart"],
    },
]


def test_natural_language_skill_matching_p50_fixtures():
    fixtures = [
        ("save this article into my knowledge base as a markdown note", "llm-wiki"),
        ("generate a product mockup image for this console idea", "imagegen"),
        ("help me learn this project and explain the codebase modules", "project-learner"),
        ("open the browser and take a screenshot after clicking login", "playwright"),
        ("extract tables from this pdf and merge the appendix", "pdf"),
        ("turn this csv into a spreadsheet chart", "spreadsheets"),
    ]

    for message, expected in fixtures:
        match = natural_language_skill_matching(message, SKILLS)
        assert match is not None
        assert match.skill_name == expected
        assert match.confidence >= 0.34
        assert match.matched_by == "natural_language"


def test_natural_language_skill_matching_low_confidence_falls_back():
    assert match_skill_for_message("please answer this normal chat question", SKILLS) is None
    assert natural_language_skill_matching("generate image", SKILLS, enabled=False) is None


def test_skill_match_narration_is_brief_and_names_skill():
    match = natural_language_skill_matching("extract tables from this pdf", SKILLS)
    assert match is not None

    narration = skill_match_narration(match, "extract tables from this pdf")

    assert narration == "我会用 skill pdf 来完成：extract tables from this pdf"
    assert len(narration) < 80
