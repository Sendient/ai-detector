# RBAC and Role Management Plan

## 1. Current State

- **Authentication:**  
  - All access is authenticated via Kinde.  
  - Only users with a valid Kinde token can access the platform.

- **User Types:**  
  - Only teachers can log in and use the platform at launch.
  - Students are not users; they are records owned by teachers.

- **Roles in the Frontend:**  
  - Roles such as "teacher", "tutor", "lecturer", "administrator", "other" are collected from users during onboarding/profile.
  - These roles are stored as strings in the database for analytics and reporting only.
  - They are **not** used for backend authorization or access control.

- **Resource Ownership:**  
  - All resources (students, class groups, assignments, documents) have a `teacher_id` field, which is currently the Kinde user ID.
  - Teachers can only access (CRUD) their own resources.

- **Soft Delete:**  
  - Soft-deleted records are invisible to all users except (future) admins.

## 2. Near-Term Improvements

- **Admin Users:**  
  - Admin users will be introduced in the future.
  - Admin status will be stored in the database (e.g., an `is_admin` boolean or a `security_role` field).
  - Admins will have access to all resources, including soft-deleted ones.

- **Internal Teacher IDs:**  
  - Introduce an internal UUID (`_id`) for each teacher, in addition to the Kinde user ID (`kinde_id`).
  - All resource ownership fields (`teacher_id`) should reference the internal UUID, not the Kinde ID.
  - When authenticating, map the Kinde ID from the token to the internal UUID for access checks.

## 3. Future-Proofing for RBAC

- **Separate Analytics and Security Roles:**  
  - Continue to collect and store the current roles for analytics (`profile_role`).
  - Add a new field for security roles (e.g., `security_roles: List[str]`), to be used for RBAC when needed.
  - Example security roles: `["admin"]`, `["teacher"]`, etc.

- **Role Management:**  
  - Security roles will be managed via the admin UI or backend scripts, not by users themselves.

- **API Documentation:**  
  - Clearly document which endpoints are accessible to which user types.
  - For now, all endpoints are "teacher only".
  - In the future, admin-only endpoints will be marked as such.

## 4. Migration Steps (for Internal UUIDs)

1. Add an internal UUID (`_id`) to the teacher model.
2. Add a `kinde_id` field to the teacher model for mapping.
3. Update all resource models to reference the teacher's internal UUID.
4. Update all CRUD and authorization logic to use the internal UUID for ownership checks.
5. Provide a migration script to update existing records to use the new reference.
6. Update authentication logic to map Kinde ID to internal UUID on each request.

## 5. Summary Table

| Field           | Purpose                | Used for RBAC? | Used for Analytics? |
|-----------------|------------------------|:--------------:|:------------------:|
| `profile_role`  | User's self-identified role (teacher, tutor, etc.) | No | Yes |
| `security_roles`| List of roles for access control (admin, teacher, etc.) | Yes (future) | No |
| `kinde_id`      | External ID from Kinde | No | No |
| `_id` (UUID)    | Internal unique ID     | Yes | No |

---

**This plan ensures analytics and security are cleanly separated, supports future RBAC, and allows for admin expansion and provider flexibility.** 