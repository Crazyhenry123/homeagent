# HomeAgent Documentation

## Documents

| Document | Audience | Description |
|----------|----------|-------------|
| [Architecture](ARCHITECTURE.md) | Engineers, Architects | System design, deployment topology, data model, tech stack |
| [API Reference](API.md) | Backend/Mobile Developers | All endpoints with request/response formats |
| [Deployment Guide](DEPLOYMENT.md) | DevOps, Admins | AWS setup, pipeline, scaling, monitoring, rollback |
| [Developer Guide](DEVELOPMENT.md) | Contributors | Local setup, testing, code conventions, adding features |
| [User Manual](USER_MANUAL.md) | End Users, Family Admins | How to install, register, chat, manage the app |
| [Test Guide](../TEST_GUIDE.md) | QA, Mobile Testers | Manual iOS test cases for all features (17 scenarios) |

## Quick Links

- **Backend health:** `curl http://<ALB-URL>/health`
- **Pipeline console:** [CodePipeline](https://console.aws.amazon.com/codesuite/codepipeline/pipelines/homeagent-pipeline/)
- **Logs:** `aws logs tail /ecs/homeagent --follow`
- **GitHub:** [Crazyhenry123/homeagent](https://github.com/Crazyhenry123/homeagent)

## New Developer Quick Start

1. Read [Architecture](ARCHITECTURE.md) for the big picture (system design, data model, request flows)
2. Follow [Developer Guide](DEVELOPMENT.md) to set up your local environment
3. Read [API Reference](API.md) for endpoint details
4. Run the test suite: `cd backend && python -m pytest tests/ -v` (158 tests)
5. Review [Test Guide](../TEST_GUIDE.md) for manual QA test cases
