CREATE TABLE "projects"(
    "id" BIGINT NOT NULL,
    "creator_id" BIGINT NOT NULL,
    "color" VARCHAR(255) NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "description" TEXT NOT NULL,
    "created_at" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL DEFAULT 'NOW()',
    "paused_at" TIMESTAMP(0) WITHOUT TIME ZONE NULL,
    "finished_at" TIMESTAMP(0) WITHOUT TIME ZONE NULL
);
ALTER TABLE
    "projects" ADD PRIMARY KEY("id");
COMMENT
ON COLUMN
    "projects"."paused_at" IS 'Дата приостановки проекта';
COMMENT
ON COLUMN
    "projects"."finished_at" IS 'Дата окочания проекта';
CREATE TABLE "tasks"(
    "id" BIGINT NOT NULL,
    "project_id" BIGINT NOT NULL,
    "parent_task_id" BIGINT NULL,
    "priority" BIGINT NOT NULL,
    "grade" FLOAT(53) NOT NULL,
    "story_points" FLOAT(53) NOT NULL,
    "created_at" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL DEFAULT 'NOW()',
    "started_at" TIMESTAMP(0) WITHOUT TIME ZONE NULL,
    "ended_at" TIMESTAMP(0) WITHOUT TIME ZONE NULL
);
ALTER TABLE
    "tasks" ADD PRIMARY KEY("id");
CREATE TABLE "users"(
    "id" BIGINT NOT NULL,
    "slug" VARCHAR(255) NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "surname" VARCHAR(255) NOT NULL,
    "patronymic" VARCHAR(255) NULL,
    "password" VARCHAR(255) NOT NULL,
    "role_id" BIGINT NOT NULL,
    "avatar_url" VARCHAR(255) NOT NULL,
    "organization" BOOLEAN NOT NULL DEFAULT '0',
    "confirmed" BOOLEAN NOT NULL DEFAULT '0',
    "created_at" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL DEFAULT 'NOW()'
);
ALTER TABLE
    "users" ADD PRIMARY KEY("id");
ALTER TABLE
    "users" ADD CONSTRAINT "users_slug_unique" UNIQUE("slug");
COMMENT
ON COLUMN
    "users"."role_id" IS 'Пользователь может иметь только одну роль';
COMMENT
ON COLUMN
    "users"."organization" IS 'Это организация?';
COMMENT
ON COLUMN
    "users"."confirmed" IS 'Это подтверждено?';
CREATE TABLE "user_to_task"(
    "user_id" BIGINT NOT NULL,
    "task_id" BIGINT NOT NULL
);
ALTER TABLE
    "user_to_task" ADD PRIMARY KEY("user_id");
ALTER TABLE
    "user_to_task" ADD PRIMARY KEY("task_id");
CREATE TABLE "user_to_project"(
    "user_id" BIGINT NOT NULL,
    "project_id" BIGINT NOT NULL
);
ALTER TABLE
    "user_to_project" ADD PRIMARY KEY("user_id");
ALTER TABLE
    "user_to_project" ADD PRIMARY KEY("project_id");
CREATE TABLE "project_roles"(
    "id" BIGINT NOT NULL,
    "slug" VARCHAR(255) NOT NULL,
    "project_id" BIGINT NOT NULL,
    "name" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "project_roles" ADD PRIMARY KEY("id");
CREATE INDEX "project_roles_slug_index" ON
    "project_roles"("slug");
COMMENT
ON COLUMN
    "project_roles"."slug" IS 'Служебное имя роли на проекте. Генерировать автоматически на основе name';
CREATE TABLE "project_role_permissions"(
    "id" BIGINT NOT NULL,
    "project_role_id" BIGINT NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "permission" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "project_role_permissions" ADD PRIMARY KEY("id");
COMMENT
ON COLUMN
    "project_role_permissions"."name" IS 'Человеческое название разрешения';
COMMENT
ON COLUMN
    "project_role_permissions"."permission" IS 'Разрешение. Должно совпадать со значением на бэкенде';
CREATE TABLE "roles"(
    "id" BIGINT NOT NULL,
    "slug" VARCHAR(255) NOT NULL,
    "name" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "roles" ADD PRIMARY KEY("id");
ALTER TABLE
    "roles" ADD CONSTRAINT "roles_slug_unique" UNIQUE("slug");
COMMENT
ON COLUMN
    "roles"."slug" IS 'Служебное имя роли в системе';
CREATE TABLE "project_role_to_user"(
    "user_id" BIGINT NOT NULL,
    "project_role_id" BIGINT NOT NULL
);
ALTER TABLE
    "project_role_to_user" ADD PRIMARY KEY("user_id");
ALTER TABLE
    "tasks" ADD CONSTRAINT "tasks_project_id_foreign" FOREIGN KEY("project_id") REFERENCES "projects"("id");
ALTER TABLE
    "tasks" ADD CONSTRAINT "tasks_parent_task_id_foreign" FOREIGN KEY("parent_task_id") REFERENCES "tasks"("id");
ALTER TABLE
    "users" ADD CONSTRAINT "users_role_id_foreign" FOREIGN KEY("role_id") REFERENCES "roles"("id");
ALTER TABLE
    "user_to_project" ADD CONSTRAINT "user_to_project_project_id_foreign" FOREIGN KEY("project_id") REFERENCES "projects"("id");
ALTER TABLE
    "project_role_to_user" ADD CONSTRAINT "project_role_to_user_user_id_foreign" FOREIGN KEY("user_id") REFERENCES "users"("id");
ALTER TABLE
    "projects" ADD CONSTRAINT "projects_creator_id_foreign" FOREIGN KEY("creator_id") REFERENCES "users"("id");
ALTER TABLE
    "project_role_permissions" ADD CONSTRAINT "project_role_permissions_project_role_id_foreign" FOREIGN KEY("project_role_id") REFERENCES "project_roles"("id");
ALTER TABLE
    "user_to_project" ADD CONSTRAINT "user_to_project_user_id_foreign" FOREIGN KEY("user_id") REFERENCES "users"("id");
ALTER TABLE
    "user_to_task" ADD CONSTRAINT "user_to_task_task_id_foreign" FOREIGN KEY("task_id") REFERENCES "tasks"("id");
ALTER TABLE
    "project_roles" ADD CONSTRAINT "project_roles_project_id_foreign" FOREIGN KEY("project_id") REFERENCES "projects"("id");
ALTER TABLE
    "project_role_to_user" ADD CONSTRAINT "project_role_to_user_project_role_id_foreign" FOREIGN KEY("project_role_id") REFERENCES "project_roles"("id");
ALTER TABLE
    "user_to_task" ADD CONSTRAINT "user_to_task_user_id_foreign" FOREIGN KEY("user_id") REFERENCES "users"("id");