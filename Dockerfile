FROM python:3.8

ENV PIP_DISABLE_PIP_VERSION_CHECK=on \
    POETRY_VERSION=1.1.4

RUN pip install "poetry==$POETRY_VERSION"

WORKDIR /slackonar

COPY . /slackonar

RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi
RUN chmod a+x ./slackonar.py

ENTRYPOINT [ "./slackonar.py" ]