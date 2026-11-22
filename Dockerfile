# The scorer builds this on linux/amd64 and runs it with no network. The
# digest is the image we labeled every commit in: its Python and SQLite
# decide which sqlglot tests run, so keep it if your image runs them.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS selector
COPY selector.py hybrid.py semantic.py impact.py predicate.py numeric.py evidence.gz lines.gz predicates.gz structural.py structural.gz tests.gz SQLGlot-LICENSE /app/
CMD ["python", "/app/selector.py"]

# Optional experimental image with the locked organizer test runner.
FROM selector AS verifier
COPY blast-radius-sample/requirements.lock /opt/requirements.lock
RUN pip install --no-cache-dir -r /opt/requirements.lock
ADD --checksum=sha256:93b2445f15f395b81c20556777ece19a6c7507df950f13fa9fac4a3be739af0d https://codeload.github.com/tobymao/sqlglot/tar.gz/eb11aec4be8cb2122afe713a4816662c3f0fb2fa /tmp/sqlglot.tar.gz
RUN mkdir -p /opt/sqlglot && tar -xzf /tmp/sqlglot.tar.gz --strip-components=1 -C /opt/sqlglot && rm /tmp/sqlglot.tar.gz
COPY verifier.py probes.py fingerprints.py /app/
CMD ["python", "/app/verifier.py"]

FROM selector AS production
