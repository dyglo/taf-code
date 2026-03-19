# TAF Code — Terminal Assistant Framework

![TAF Code Banner](https://github.com/dyglo/taf-code/blob/main/taf-logo.png?raw=true)

TAF Code is a premium, AI-powered coding assistant designed to live in your terminal. It provides a highly interactive experience with rich UI components, real-time feedback, and powerful file-system tools.

## Key Features

- ╭──╮ **Bordered Input Box**: A focused, premium command-line experience.
- ⌛ **Real-time Spinner**: Animated processing indicator with an elapsed timer for all operations.
- ⚡ **Rich Markdown**: Clean terminal rendering of AI responses (bolding, lists, code blocks) without raw symbols.
- 🚀 **NPM & Pip Ready**: Install it via your preferred package manager.
- **Rich Inline Diffs**: Custom line-by-line diff previews for every file modification.
- **Smart Update Checker**: Automatically notifies you when a new version of `taf-cli` is released on npm.
- **Interactive Bash**: Support for TTY-based interactive commands (like `npx` or `git`) directly within the session.

## Installation

### Via npm (Recommended)
```bash
npm install -g taf-cli
```

### Via pip
```bash
pip install taf-code
```

## Usage

Simply run:
```bash
taf
```

### Configuration
Set your Gemini API key:
```bash
taf config --api-key YOUR_KEY
```

### Managing Updates
TAF Code checks for updates every 24 hours. To manually update at any time:
```bash
npm install -g taf-cli@latest
```

### Tip: Interactive Commands
When asking TAF Code to run commands like `npx create-next-app`, it will now correctly pass through your keyboard input for any interactive prompts (Y/n).

## License
MIT
