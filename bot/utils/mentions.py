import re


_FILTERED_INVITATION_MENTION = re.compile(r'<@&?[0-9]+>|@(?:everyone|here)')


def strip_discord_mentions(text: str) -> str:
    """Strip invitation mentions, retaining <@!ID> for display only.

    Callers must also restrict allowed_mentions when sending or editing.
    """
    # A space prevents inputs such as @eve<@123>ryone becoming a new mention.
    # Ordinary @names, email addresses, and channel links are not ping syntax.
    return _FILTERED_INVITATION_MENTION.sub(' ', text).strip()
