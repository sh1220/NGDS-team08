# 이미지는 홈랩 노드(x86_64)용으로 빌드한다. 맥(arm64)에서도 --platform 으로 맞춘다.
IMAGE ?= ghcr.io/sh1220/ngds-team08-mcp
TAG   ?= $(shell git rev-parse --short HEAD)
NS    ?= chabunsi

.PHONY: build push deploy undeploy status logs cluster-init run
build:         ## 이미지 빌드
	docker build --platform linux/amd64 -t $(IMAGE):$(TAG) .
push: build    ## GHCR에 올리기 (docker login ghcr.io 필요)
	docker push $(IMAGE):$(TAG)
deploy:        ## 클러스터에 배포/업데이트
	helm upgrade --install chabunsi charts/chabunsi -n $(NS) --set image.tag=$(TAG) --wait
undeploy:      ## 클러스터에서 삭제
	helm uninstall chabunsi -n $(NS)
status:
	kubectl -n $(NS) get pods,svc
logs:
	kubectl -n $(NS) logs deploy/chabunsi -f
cluster-init:  ## (관리자 1회) 네임스페이스·팀원 권한
	kubectl apply -f cluster/namespace-rbac.yaml
run:           ## 로컬 실행: http://localhost:8000/mcp
	cd app && python server.py
