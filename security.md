# FloatChat — Security Guidelines

## 1. Overview
FloatChat is a student mini project with no user authentication.
However these basic security rules must still be followed.

---

## 2. Environment Variables
- NEVER hardcode passwords, DB credentials, or API keys in code
- Always load from .env file using python-dotenv
- Never commit .env to GitHub — add to .gitignore immediately
- Use .env.example with empty values for reference

```bash
# .gitignore must include
.env
*.env
data/cache/
__pycache__/
*.pyc
venv/
```

---

## 3. SQL Injection Prevention
- NEVER use f-strings or string concatenation to build SQL
- Always use parameterized queries with psycopg2

```python
# WRONG — vulnerable to SQL injection
query = f"SELECT * FROM profiles WHERE wmo_id = {user_input}"

# CORRECT — parameterized query
query = "SELECT * FROM profiles WHERE wmo_id = %s"
cursor.execute(query, (user_input,))
```

- This is enforced by the template system — templates use parameterized queries only

---

## 4. Input Validation
- All user queries pass through validator.py before processing
- Reject queries longer than 500 characters
- Strip HTML tags and special characters from input
- Validate WMO IDs are integers only
- Validate lat/lon are within valid ranges (-90 to 90, -180 to 180)
- Validate dates are in correct format (YYYY-MM-DD)

```python
def sanitize_input(text):
    text = text.strip()
    if len(text) > 500:
        raise ValueError("Query too long")
    # Remove HTML tags
    import re
    text = re.sub(r'<[^>]+>', '', text)
    return text
```

---

## 5. API Rate Limiting
- Argovis API has rate limits — use query cache to avoid repeated calls
- Cache TTL set to 24 hours for same query parameters
- Log all failed API calls for debugging

---

## 6. Data Privacy
- FloatChat only uses public ARGO data — no private user data stored
- No user login — no personal information collected
- Session memory cleared when browser tab is closed
- No analytics or tracking

---

## 7. Dependency Security
- Pin all package versions in requirements.txt
- Run pip audit periodically to check for vulnerabilities
```bash
pip install pip-audit
pip-audit
```

---

## 8. Deployment Security (Streamlit Cloud)
- Store all secrets in Streamlit Cloud Secrets Manager
- Never expose DB credentials in public GitHub repo
- Use read-only DB user for the app (no DROP/DELETE permissions)

```sql
-- Create read-only app user
CREATE USER floatchat_app WITH PASSWORD 'yourpassword';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO floatchat_app;
```
