---
id: D-0003
project_id: pit
title: pithub 기술 스택 - FastAPI + Next.js
status: active
created_at: 2025-12-12T21:30:00+09:00
---

# pithub 기술 스택 결정: FastAPI + Next.js

## 배경

pithub는 GitHub repo의 .pit/ 폴더를 웹으로 시각화하는 서비스.
여러 기술 스택 옵션 중 선택이 필요했음.

## 결정

**FastAPI (백엔드) + Next.js (프론트엔드)**

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│   Next.js       │────▶│   FastAPI        │────▶│  GitHub API │
│   (Frontend)    │     │   (Backend)      │     │  .pit/ 읽기 │
│   pithub.io     │     │   api.pithub.io  │     │             │
└─────────────────┘     └──────────────────┘     └─────────────┘
```

## 이유

### FastAPI 선택 이유
1. **Python**: pit CLI와 동일 언어, 코드 재사용 가능
   - `pit.loaders`, `pit.models` 직접 import
2. **빠름**: 비동기, 고성능
3. **OpenAPI**: 자동 문서화, 프론트엔드 타입 생성 용이
4. **GitHub API**: `httpx` 등으로 쉽게 연동

### Next.js 선택 이유
1. **SSR/SSG**: SEO, 빠른 초기 로딩
2. **React**: 컴포넌트 기반, 풍부한 생태계
3. **Vercel**: 쉬운 배포
4. **TypeScript**: 타입 안정성

## 대안 검토

| 옵션 | 장점 | 단점 | 결정 |
|------|------|------|------|
| Next.js API Routes | 단일 앱 | Python 코드 재사용 불가 | ❌ |
| Astro | 정적 최적화 | 동적 기능 제한 | ❌ |
| GitHub Pages | 무료, 심플 | 백엔드 없음 | ❌ |
| **FastAPI + Next.js** | 유연, 코드 재사용 | 두 앱 관리 | ✅ |

## 구조

```
pit/
├── pit/           # CLI (기존)
├── pithub/
│   ├── api/       # FastAPI 백엔드
│   │   ├── main.py
│   │   ├── routers/
│   │   └── services/
│   └── web/       # Next.js 프론트엔드
│       ├── app/
│       └── components/
```

## 영향

- 두 개의 배포 대상 (api.pithub.io, pithub.io)
- Python + Node.js 모두 필요
- pit 코드 재사용으로 개발 속도 향상
