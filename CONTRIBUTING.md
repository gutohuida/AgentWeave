# Contributing to AgentWeave

Thank you for your interest in contributing to AgentWeave! This document provides guidelines for contributing.

---

## 🚀 Quick Start

1. **Fork the repository**
2. **Clone your fork**
   ```bash
   git clone https://github.com/yourusername/agentweave.git
   cd agentweave
   ```
3. **Install in development mode**
   ```bash
   pip install -e ".[dev]"
   ```
4. **Create a branch**
   ```bash
   git checkout -b feature/my-feature
   ```

---

## 📋 Development Setup

### Prerequisites

- Python 3.8+
- Git

### Install Dependencies

```bash
pip install -e ".[dev]"
```

This installs:
- `pytest` - Testing
- `black` - Code formatting
- `ruff` - Linting
- `mypy` - Type checking

---

## 🧪 Testing

Run tests with:

```bash
pytest
```

With coverage:

```bash
pytest --cov=agentweave
```

---

## 🎨 Code Style

### Formatting

We use `black` for code formatting:

```bash
black src/ tests/
```

### Linting

We use `ruff` for linting:

```bash
ruff check src/ tests/
```

### Type Checking

We use `mypy` for type checking:

```bash
mypy src/
```

### Pre-commit

Run all checks:

```bash
black src/ tests/
ruff check src/ tests/
mypy src/
pytest
```

---

## 📝 Commit Messages

Use clear, descriptive commit messages:

- ✅ `feat: add task priority levels`
- ✅ `fix: handle missing session file`
- ✅ `docs: update README with examples`
- ✅ `refactor: simplify task creation`

---

## 🐛 Reporting Bugs

When reporting bugs, please include:

1. **Python version**
2. **Operating system**
3. **Steps to reproduce**
4. **Expected behavior**
5. **Actual behavior**
6. **Error messages** (if any)

---

## 💡 Suggesting Features

We welcome feature suggestions! Please:

1. Check if the feature is already requested
2. Describe the use case
3. Explain why it would be useful
4. Provide examples if possible

---

## 🔀 Pull Request Process

1. **Update documentation** if needed
2. **Add tests** for new features
3. **Ensure all tests pass**
4. **Update CHANGELOG.md** if applicable
5. **Submit PR** with clear description

### PR Checklist

- [ ] Tests pass
- [ ] Code is formatted with black
- [ ] Linting passes with ruff
- [ ] Type checking passes with mypy
- [ ] Documentation updated
- [ ] CHANGELOG.md updated (if applicable)

---

## 📁 Project Structure

```
agentweave/
├── src/agentweave/          # Main package
│   ├── __init__.py
│   ├── cli.py               # CLI
│   ├── session.py           # Session management
│   ├── task.py              # Task management
│   ├── messaging.py         # Messaging
│   ├── constants.py         # Constants
│   ├── utils.py             # Utilities
│   └── templates/           # Templates
├── tests/                   # Tests
└── docs/                    # Documentation
```

---

## 🎯 Areas for Contribution

### High Priority

- [ ] Add more comprehensive tests
- [ ] Improve error handling
- [ ] Add more templates
- [ ] Web dashboard for collaboration

### Medium Priority

- [ ] Slack/Discord integration
- [ ] Desktop notifications
- [ ] Additional agent profiles
- [ ] Export to PDF/HTML

### Low Priority

- [ ] VS Code extension
- [ ] More CLI commands
- [ ] Plugin system

---

## 📜 Code of Conduct

Be respectful, inclusive, and constructive.

---

## ❓ Questions?

- **Issues:** [GitHub Issues](https://github.com/yourusername/agentweave/issues)
- **Discussions:** [GitHub Discussions](https://github.com/yourusername/agentweave/discussions)

---

Thank you for contributing! 🎉
