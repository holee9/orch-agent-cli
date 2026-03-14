# 사용자 인증 시스템

## 프로젝트
사용자 인증 및 권한 관리 시스템 개발

## 배경
기존 세션 기반 인증 시스템의 보안 취약점이 발견되어 JWT 기반으로 전환 필요

## 목표
- JWT 기반 인증 시스템 구현
- Role-based access control (RBAC) 도입
- OAuth 2.0 소셜 로그인 지원

## 범위
### 포함
- 로그인/로그아웃 API
- JWT 토큰 발급 및 갱신
- RBAC 미들웨어

### 제외
- UI/UX 디자인
- 모바일 앱 지원

## 제약사항
- Python 3.10+ 필수
- 기존 데이터베이스 스키마 유지
- 하위 호환성 보장

## 기술스택
- 언어: Python 3.10+
- 프레임워크: FastAPI
- 데이터베이스: PostgreSQL
- 기타: Redis (세션 캐시), Docker

## 참고자료
- OWASP Authentication Cheat Sheet
- JWT RFC 7519

## 우선순위
- P0 (필수): JWT 인증, 로그인 API
- P1 (높음): RBAC, 토큰 갱신
- P2 (보통): OAuth 소셜 로그인

## 일정
- 시작일: 2026-03-15
- 마감일: 2026-04-15
- 마일스톤: 3월 말 MVP 완성
