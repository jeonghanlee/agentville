FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-server openssh-client procps && apt-get clean
RUN useradd --create-home --uid 1000 dev && mkdir -p /run/sshd && ssh-keygen -A
WORKDIR /workspace/agentville
COPY pyproject.toml .
COPY packages packages
RUN pip install .
RUN chown -R dev:dev /workspace/agentville
COPY authorized_keys /home/dev/.ssh/authorized_keys
RUN chown -R dev:dev /home/dev/.ssh && chmod 700 /home/dev/.ssh && chmod 600 /home/dev/.ssh/authorized_keys
COPY agent.py /verification/agent.py
ENV HOME=/home/dev
