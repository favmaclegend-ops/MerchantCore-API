# Contributing to Merchant Core API

Thank you for your interest in contributing to Merchant Core API! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in the [Issues](https://github.com/your-repo/issues)
2. If not, create a new issue with:
   - Clear description of the bug
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots (if applicable)
   - Environment details (OS, Python version, etc.)

### Suggesting Enhancements

1. Check existing issues and discussions
2. Create a new issue with:
   - Clear description of the enhancement
   - Use case and benefits
   - Possible implementation approach (optional)

### Pull Requests

1. **Fork** the repository
2. **Clone** your fork locally
3. **Create a branch** for your feature/fix:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```
4. **Make your changes**
5. **Test** your changes thoroughly
6. **Commit** with clear, descriptive messages:
   ```bash
   git commit -m "feat: add user profile endpoint"
   # or
   git commit -m "fix: resolve email verification issue"
   ```
7. **Push** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
8. **Create a Pull Request** to the main repository

## Development Setup

1. Fork and clone the repository
2. Install dependencies:
   ```bash
   uv sync
   ```
3. Create a `.env` file from `.env.example`
4. Run the development server:
   ```bash
   uv run fastapi dev main.py
   ```

## Coding Standards

### Python Style Guide

- Follow [PEP 8](https://pep8.org/) style guide
- Use type hints where possible
- Write docstrings for functions and classes

### Code Quality

- Keep functions small and focused
- Use meaningful variable and function names
- Avoid hardcoded values; use configuration
- Handle errors gracefully with appropriate exceptions

### Commit Messages

Use conventional commit format:
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, etc.)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

Example:
```
feat: add password reset endpoint

- Added POST /auth/reset-password endpoint
- Added token generation for password reset
- Updated email service to send reset emails
```

## Testing

- Write tests for new features and bug fixes
- Ensure all tests pass before submitting PR
- Aim for good test coverage

Run tests:
```bash
pytest
```

## Documentation

- Update README.md if adding new features
- Add docstrings to new functions and classes
- Update API documentation if changing endpoints

## Review Process

1. All PRs require at least one review
2. Address review feedback promptly
3. Keep PRs focused on a single feature/fix
4. Rebase if there are conflicts with the main branch

## Questions?

Feel free to open an issue for any questions about contributing.

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
