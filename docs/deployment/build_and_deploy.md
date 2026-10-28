### Automated deploy (GitHub Actions)

Pushes to `feat/arch-change` run `.github/workflows/deploy.yml`, which builds the
image, pushes `madhav69/symptom-sync:<sha>` to Docker Hub and updates the
`symptom-sync` container app using `azure/container-apps-deploy-action`.

Azure auth uses OIDC (no stored client secret). Required repository secrets:
`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `DOCKERHUB_USERNAME`,
`DOCKERHUB_TOKEN`.

The federated credential configuration is saved in [federated.json](federated.json).

One-time Azure setup: create an app registration / service principal with
Contributor on the `symptom-sync` resource group, and add a federated credential
(issuer `https://token.actions.githubusercontent.com`, subject
`repo:<owner>/<repo>:ref:refs/heads/feat/arch-change`, audience `api://AzureADTokenExchange`).

### Build and push the Image (manual)
```
IMAGE=madhav69/symptom-sync
TAG=$(date +%Y%m%d-%H%M%S)

docker build -t $IMAGE:$TAG -t $IMAGE:latest .
```
```
docker push $IMAGE:$TAG
```
### Update running azure container app

```
az containerapp update \
  --name symptom-sync \
  --resource-group symptom-sync \
  --image $IMAGE:$TAG
```
### Check if its updated

```
az containerapp list --query "[].{AppName:name, ResourceGroup:resourceGroup, Image:properties.template.containers[0].image}" --output table

```
