# 사용자 로그인 기능 추가

## 프로젝트
my-web-app — FastAPI 기반 RESTful API 서버

## 배경
현재 API는 인증 없이 누구나 호출 가능하다.
사용자 계정 시스템을 추가하여 인증된 사용자만 데이터를 읽고 쓸 수 있어야 한다.

## 목표
- 이메일/비밀번호 기반 회원가입 및 로그인 API 구현
- JWT 토큰 발급 및 검증 미들웨어 추가
- 기존 API 엔드포인트에 인증 적용

## 범위
### 포함
- `POST /auth/register` — 회원가입 (이메일, 비밀번호)
- `POST /auth/login` — 로그인 (이메일, 비밀번호 → JWT 반환)
- `GET /auth/me` — 현재 로그인 사용자 정보 조회
- JWT Bearer 토큰 검증 미들웨어
- 기존 `/items` 엔드포인트에 인증 필요 조건 추가

### 제외
- OAuth2 소셜 로그인 (Google, GitHub)
- 이메일 인증 발송
- 비밀번호 재설정 기능

## 제약사항
- 기술: Python 3.11+, FastAPI, SQLAlchemy (이미 사용 중)
- 데이터베이스: 기존 PostgreSQL 인스턴스 사용 (새 DB 생성 불가)
- 보안: 비밀번호는 bcrypt 해시 저장, JWT는 HS256 알고리즘 사용

## 기술스택
- 언어: Python 3.11
- 프레임워크: FastAPI 0.110
- 데이터베이스: PostgreSQL 15 (SQLAlchemy ORM)
- 인증: python-jose (JWT), passlib (bcrypt)

## 참고자료
- 기존 API 구조: `src/api/routes.py`
- 데이터베이스 모델: `src/db/models.py`
- FastAPI 공식 인증 가이드: https://fastapi.tiangolo.com/tutorial/security/

## 우선순위
- P0 (필수): 회원가입, 로그인 API, JWT 미들웨어
- P1 (높음): `/items` 엔드포인트 인증 적용
- P2 (보통): `/auth/me` 엔드포인트

## 일정
- 시작일: 2026-03-15
- 마감일: 2026-03-17
- 마일스톤: 로그인 API 완성 → 미들웨어 적용 → 테스트 통과
