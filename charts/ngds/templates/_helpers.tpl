{{- define "so.labels" -}}
app.kubernetes.io/name: {{ . }}
app.kubernetes.io/part-of: ngds
{{- end }}
{{/* Pod Security restricted: 컨테이너 공통 */}}
{{- define "so.containerSecurity" -}}
securityContext:
  allowPrivilegeEscalation: false
  capabilities: {drop: [ALL]}
{{- end }}
{{/* Pod Security restricted: 파드 공통. 인자 = 이미지 안의 실행 uid */}}
{{- define "so.podSecurity" -}}
securityContext:
  runAsNonRoot: true
  runAsUser: {{ . }}
  runAsGroup: {{ . }}
  fsGroup: {{ . }}
  seccompProfile: {type: RuntimeDefault}
{{- end }}
