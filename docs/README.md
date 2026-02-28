# HomeAgent Documentation

## Documents

| Document | Audience | Description |
|----------|----------|-------------|
| [Architecture](ARCHITECTURE.md) | Engineers, Architects | System design, deployment topology, data model, tech stack |
| [API Reference](API.md) | Backend/Mobile Developers | All endpoints with request/response formats |
| [Deployment Guide](DEPLOYMENT.md) | DevOps, Admins | AWS setup, pipeline, scaling, monitoring, rollback |
| [User Manual](USER_MANUAL.md) | End Users, Family Admins | How to install, register, chat, manage the app |
| [Developer Guide](DEVELOPMENT.md) | Contributors | Local setup, testing, code conventions, adding features |

## Quick Links

- **Backend health:** `curl http://<ALB-URL>/health`
- **Pipeline console:** [CodePipeline](https://console.aws.amazon.com/codesuite/codepipeline/pipelines/homeagent-pipeline/)
- **Logs:** `aws logs tail /ecs/homeagent --follow`
- **GitHub:** [Crazyhenry123/homeagent](https://github.com/Crazyhenry123/homeagent)
