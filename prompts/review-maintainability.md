## Your focus: maintainability and anti-slop

Look for duplicated code (including code that repeats something that already exists in `<touched_files>` or `<callers>`), dead or unreachable code, leftover debug output, needless verbosity and over-engineering, comments that restate the code or no longer match it, misleading names, and changes that erode the existing structure of the code. Do not report pure taste; a nit must still make the code clearer.
