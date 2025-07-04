# Hinata – Project Root Quick Reference

Welcome to Hinata, a modular, command-line-first suite of tools for interacting with Large Language Models (LLMs). This document provides a high-level map of the entire project.

**Start here** to understand the big picture, then dive into the `HINATA.md` files within each subdirectory for component-specific details.

## What is Hinata?

Hinata is not a single application, but a collection of small, sharp, composable tools designed to bring LLM capabilities into a traditional developer workflow. The philosophy is to create powerful, scriptable utilities that work together, rather than a monolithic GUI.

The project is organized into distinct layers, with low-level C binaries providing core functionality and higher-level Python scripts orchestrating them into useful applications.

## Component Layers & How They Fit

The project follows a clear dependency chain. Higher layers build upon and use the tools provided by the layers below them.

```
+-----------+      +-----------+      +-----------+
|  web/     |      |  edit/    |      |  agent/   |   (User-Facing Applications)
| (Web UI)  |      |  (Code   |      | (Shell &   |
|           |      |   Editor) |      |   Browser) |
+-----+-----+      +-----+-----+      +-----+-----+
      |                  |                  |
      |   (uses CLI)     |   (uses CLI)     |   (uses CLI)
      +------------------+------------------+
                         |
                         v
+----------------------------------------------------+
|               chat/  (hnt-chat)                    |   (Conversation Management)
+----------------------------------------------------+
                         |
                         | (uses CLI)
                         v
+----------------------------------------------------+
|                 llm/   (hnt-llm)                   |   (Core LLM API Interface)
+----------------------------------------------------+
                         |
                         | (HTTPS to external API)
                         v
                 +-------------------+
                 |   3rd-Party LLM   |
                 +-------------------+
```

### The Layers Explained

1.  **`llm/` – The Engine**
    *   **What:** Provides the foundational `hnt-llm` C binary.
    *   **Job:** Takes text from `stdin`, sends it to a remote LLM API (OpenAI, Claude, etc.), and streams the response to `stdout`. It is the project's only direct link to the outside LLM world.
    *   **Dive Deeper:** `llm/HINATA.md`

2.  **`chat/` – The Conversation Hub**
    *   **What:** The `hnt-chat` Python script.
    *   **Job:** Wraps `hnt-llm` to add state. It manages conversation history, storing messages as simple files on disk. Nearly all other tools in Hinata use `hnt-chat` instead of calling `hnt-llm` directly.
    *   **Dive Deeper:** `chat/HINATA.md`

3.  **Application Layers – The User-Facing Tools**
    These components are distinct applications built on the `chat` layer.

    *   **`edit/` – LLM-Powered Code Editing**
        *   **Tools:** `hnt-edit`, `llm-pack`, `hnt-apply`.
        *   **Workflow:** Bundles local source files, asks the LLM (via `hnt-chat`) to generate a patch, and applies it.
        *   **Dive Deeper:** `edit/HINATA.md`

    *   **`agent/` – Interactive Shell & Web Agent**
        *   **Tools:** `hnt-agent`, `headlesh` (persistent shell), `browse` (headless web scraper).
        *   **Workflow:** Creates an interactive loop where an LLM (via `hnt-chat`) can execute shell commands and browse the web to accomplish a goal.
        *   **Dive Deeper:** `agent/HINATA.md`

    *   **`web/` – Web UI for Chat**
        *   **Tools:** `hnt-web` (FastAPI server), static HTML/CSS/JS.
        *   **Workflow:** Provides a simple, local web interface for using the `hnt-chat` functionality from a browser.
        *   **Dive Deeper:** `web/HINATA.md`

---

## Getting Started: Where to Look First

*   **To build everything:** Each subdirectory has its own `build` script and `build.md` documentation. While they can be built independently, you should generally build in dependency order: `llm`, then `chat`, then the application directories.
*   **To understand the core model interface:** Start with `llm/HINATA.md`.
*   **To see how conversations are managed:** Read `chat/HINATA.md`.
*   **To work on a specific feature (editing, agent, web):** Go directly to the `HINATA.md` in the relevant subdirectory (`edit/`, `agent/`, `web/`). It will serve as your map for that component.