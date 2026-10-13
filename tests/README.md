# Tests

Regression checks, synthetic fixtures and explicit live probes. These files verify the app; they are not translation providers and do not run during normal use.

From the repository root:

```powershell
python app.py --self-test --report verification/source-tests.json
python -m unittest discover -s tests -t .
```

`--self-test` uses local fixtures and mocked service responses. `--native-self-test` executes the bundled offline models. Live benchmark and speech switches contact free services with synthetic or attributed public inputs. Never use private conversations as test data.

The packaged executable retains `--self-test`. Tests use temporary data and do not delete real saved sessions.
