"""Fit complete invitation entries into Discord's embed text budget."""

from bot.utils.i18n import t


def text_length(text: str) -> int:
    # Count astral emoji conservatively as two units, as Discord clients do.
    return len(text.encode('utf-16-le')) // 2


def fit_sections(sections: list[tuple[str, list[str]]], limit: int = 4096) -> str:
    blocks = [
        (f'\n**{heading}**\n' if index == 0 else '\n') + line
        for heading, lines in sections
        for index, line in enumerate(lines)
    ]
    description = '\n'.join(blocks)
    if text_length(description) <= limit:
        return description

    total = len(blocks)
    while blocks:
        blocks.pop()
        notice = t('teamup_display.messages.overflow', count=total - len(blocks))
        description = '\n'.join(blocks) + '\n\n' + notice
        if text_length(description) <= limit:
            return description
    return t('teamup_display.messages.overflow', count=total)
