"""Build an enriched LLM system prompt from memory database contents."""

from .persons import get_person, get_attributes
from .facts import get_facts


def build_system_prompt(base_prompt: str, person_id: int | None = None) -> str:
    """Return base_prompt extended with relevant memory context.

    Sections are only appended when data exists, so the prompt stays concise
    for fresh installations with no stored knowledge.
    """
    sections: list[str] = [base_prompt]

    if person_id is not None:
        person = get_person(person_id)
        if person and person["name"] != "Unbekannt":
            sections.append(f"\n## Memory context\nYou are currently talking to: {person['name']}.")

            attrs = get_attributes(person_id)
            if attrs:
                attr_lines = "\n".join(f"- {k}: {v}" for k, v in attrs.items())
                sections.append(f"Known attributes:\n{attr_lines}")

            person_facts = get_facts(person_id=person_id)
            if person_facts:
                fact_lines = "\n".join(f"- {f['content']}" for f in person_facts)
                sections.append(f"Notes about this person:\n{fact_lines}")

    global_facts = get_facts(person_id=None)
    if global_facts:
        fact_lines = "\n".join(f"- {f['content']}" for f in global_facts)
        header = "\n## Memory context" if person_id is None else ""
        sections.append(f"{header}\nGeneral knowledge:\n{fact_lines}")

    return "\n".join(sections)
