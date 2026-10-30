{{- define "so.labels" -}}
app.kubernetes.io/name: {{ . }}
app.kubernetes.io/part-of: ngds
{{- end }}
