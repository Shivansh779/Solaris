---
name: solaris-cli-ux
description: Improve Solaris terminal UX, Markdown rendering, tables, code blocks, status output, and overall CLI readability
license: MIT
compatibility: opencode
metadata:
  audience: Solaris maintainers
  workflow: development
---

## What I do

- Inspect Solaris' existing CLI and TUI architecture.
- Identify problems with AI response readability and terminal presentation.
- Improve Markdown rendering in the terminal.
- Render Markdown tables as readable terminal-native tables.
- Improve code-block presentation and syntax highlighting where appropriate.
- Improve headings, lists, blockquotes, links, spacing, and line wrapping.
- Improve status, progress, warning, and error presentation.
- Improve web-search source presentation where relevant.
- Research suitable terminal/UI libraries when necessary.
- Prefer a small number of capable libraries over many tiny dependencies.
- Preserve Solaris' existing architecture unless a larger change is genuinely justified.
- Test the resulting CLI experience across different response types and terminal widths.

## When to use me

Use this when improving Solaris' command-line or terminal user experience.

Use me when:

- AI responses are difficult to read.
- Markdown is being printed as raw text.
- Tables are difficult to read.
- Code blocks need better presentation.
- Long responses overflow or become difficult to navigate.
- Status/progress output needs improvement.
- Errors and warnings need clearer presentation.
- Web-search results or sources need better terminal presentation.
- The Solaris CLI needs a general UX improvement.

Do not use this skill merely to add decorative styling.

The primary objective is **readability and usability**.

## Core principle

Solaris should treat AI output as content and the terminal as the presentation layer.

Preferred architecture:

```text
AI response
    ↓
Markdown / response content
    ↓
Solaris renderer
    ↓
Terminal
```

Do not make the AI model responsible for generating ANSI escape sequences or terminal-specific formatting.

## Workflow

### 1. Inspect first

Before changing code, inspect the existing Solaris implementation.

Understand:

- current TUI architecture
- response pipeline
- response printing/rendering
- existing Markdown handling
- existing table handling
- code-block handling
- spinner/loading implementation
- status and error output
- current dependencies

Do not assume Solaris' architecture.

### 2. Identify the highest-value UX problems

Prioritize improvements roughly in this order:

1. Markdown readability
2. Tables
3. Code blocks
4. Long-response wrapping
5. Status/progress output
6. Errors and warnings
7. Sources
8. Secondary visual improvements

Solve readability problems before adding decorative features.

### 3. Research when useful

Research current terminal-rendering approaches and libraries when a dependency or architectural choice needs verification.

Potential libraries include:

- Rich
- Textual
- prompt_toolkit
- markdown-it-py
- Pygments
- other appropriate maintained Python libraries

These are suggestions, not requirements.

Choose based on Solaris' actual needs.

### 4. Minimize dependencies

Do not add a separate library for every tiny UI feature.

Prefer a small number of capable libraries that solve several related problems.

For example, if one well-maintained library can provide:

- Markdown rendering
- tables
- syntax highlighting
- terminal width handling

then prefer that over several unrelated packages.

Do not introduce a large framework merely because it is more powerful.

### 5. Preserve the existing architecture

Do not rewrite Solaris' entire TUI unless the current architecture genuinely prevents the desired UX.

Prefer incremental improvements.

For example:

```text
existing response system
        ↓
rendering layer
        ↓
Markdown
tables
code
status
sources
```

is preferable to replacing the entire application architecture without justification.

If a major architectural change appears necessary, explain why before implementing it.

## Markdown rendering

AI-generated Markdown should be rendered appropriately for the terminal.

Support where practical:

- headings
- bold
- italics
- lists
- nested lists
- blockquotes
- links
- horizontal rules
- tables
- code blocks

Do not display raw Markdown syntax when it can reasonably be rendered.

## Tables

Markdown tables should become readable terminal tables.

Consider:

- column alignment
- readable spacing
- terminal width
- long-cell wrapping
- multiline content
- narrow terminals
- large numbers of columns

Do not allow a table to make the entire terminal unreadable.

## Code blocks

Code should be visually separated from ordinary text.

Where practical:

- syntax highlight code
- preserve indentation
- preserve whitespace
- handle long lines sensibly
- distinguish code from surrounding prose

Do not over-style code.

## Long responses

Long AI responses should remain readable.

Consider:

- intelligent line wrapping
- spacing between sections
- heading hierarchy
- terminal width
- horizontal overflow
- code blocks
- tables

Do not blindly truncate useful content.

## Status and progress

Operational output should clearly communicate what Solaris is doing.

For example:

```text
● Searching the web...
✓ 5 sources found

● Reading documentation...
✓ Relevant information found

● Generating response...
```

Avoid excessive status noise.

Status messages should be concise and useful.

## Errors and warnings

Errors and warnings should be immediately distinguishable from normal output.

For example:

```text
⚠ Web search failed
  Falling back to another provider...
```

or:

```text
✗ Could not connect to provider
  Reason: ...
```

Do not rely exclusively on color to communicate meaning.

## Sources

When Solaris performs web research, sources should be presented clearly.

Prefer something conceptually similar to:

```text
Sources

[1] Python Documentation
[2] Tavily Documentation
[3] Firecrawl Documentation
```

Avoid unnecessarily dumping raw URLs throughout the response.

## Terminal compatibility

The CLI should degrade gracefully when possible.

Consider:

- narrow terminals
- terminals without color
- limited Unicode support
- different ANSI capabilities

Important information must remain understandable without styling.

## Testing

After implementation, test:

### Markdown

- headings
- bold and italic
- lists
- nested lists
- blockquotes
- links

### Tables

- short cells
- long cells
- multiple columns
- multiline cells
- narrow terminal widths

### Code

- Python
- another relevant language where appropriate
- long lines
- indentation

### Responses

- short responses
- long responses
- responses containing multiple Markdown elements

### Existing functionality

Ensure changes do not break:

- normal AI responses
- `.WEB`
- `.BETTER`
- commands
- streaming
- spinners
- errors
- model output
- existing TUI behavior

## Avoid

Do not:

- rewrite Solaris unnecessarily
- add dependencies for trivial tasks
- make everything colorful
- add animations everywhere
- make the terminal noisy
- sacrifice readability for aesthetics
- make AI models generate ANSI codes
- hard-code terminal dimensions
- assume every terminal supports color
- introduce a large UI framework without justification
- change AI/model behavior merely to solve presentation problems
- remove useful existing functionality without justification

## Definition of done

The improvement is complete when:

- AI Markdown is rendered instead of displayed raw.
- Headings are clearly distinguishable.
- Lists are readable.
- Tables are rendered as terminal-native tables.
- Tables behave reasonably in narrow terminals.
- Code blocks are clearly separated.
- Syntax highlighting is used where useful.
- Long responses wrap appropriately.
- Status/progress output is clear.
- Errors and warnings are distinguishable.
- Sources are presented cleanly.
- The CLI remains usable without color.
- Existing Solaris functionality continues working.
- Dependencies remain reasonably small.
- Tests cover the major rendering cases.

## Final principle

> Prefer the simplest solution that produces a clearly better terminal experience.

Do not optimize for maximum technical sophistication.

Optimize for a Solaris CLI that is **pleasant to read, easy to operate, and noticeably better than raw `print(response)`**.
