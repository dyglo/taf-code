# TAF Code

**TAF Code** is an AI-powered coding assistant for your terminal, meticulously designed to provide a premium user experience with a Claude Code-style interface. Powered by Google's Gemini models, it allows you to build, debug, and understand your codebase directly from your CLI.

![TAF Code Banner](https://github.com/dyglo/taf-code/blob/main/.github/preview.png?raw=true)

## Key Features

- ╭──╮ **Bordered Input Box**: A focused, premium command-line experience.
- ⚙ **Inline Diffs**: View code changes immediately with color-coded additions/removals and context line numbers.
- ⌛ **Real-time Spinner**: Animated processing indicator with an elapsed timer for all operations.
- ⚡ **Rich Markdown**: Clean terminal rendering of AI responses (bolding, lists, code blocks) without raw symbols.
- 🚀 **NPM & Pip Ready**: Install it via your preferred package manager.
- 📂 **Context Aware**: Deeply understands your project structure and files.

## Installation

### Via NPM (Recommended)
```bash
npm install -g taf-cli
```

### Via Pip (For Developers)
```bash
pip install -e .
```

## Usage

Start the assistant by typing:
```bash
taf
```
or 
```bash
taf-code
```

### Tips
- Use `! <command>` for bash mode.
- Use `/` to see available slash commands like `/help`, `/save`, or `/model`.
- Use `\=` at the end of a line for a newline.

## Configuration

Set your Gemini API Key in your environment:
```powershell
$env:GEMINI_API_KEY="your-key-here"
```
or (Unix)
```bash
export GEMINI_API_KEY="your-key-here"
```

## License
MIT
