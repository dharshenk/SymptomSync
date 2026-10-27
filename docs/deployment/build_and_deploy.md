### Build and push the Image
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
