"""Current time tool — gives the agent awareness of the current date and time."""

from strands_tools.current_time import current_time

# Re-export the built-in strands current_time tool directly.
# It's already a Strands DecoratedFunctionTool ready for use.
get_current_time = current_time
