CREATE TABLE "tasks"(
    "id" BIGSERIAL NOT NULL,
    "parent_task_id" BIGINT NULL,
    "creator_id" BIGINT NOT NULL,
    "color" VARCHAR(255) NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "description" TEXT NOT NULL,
    "priority" BIGINT NOT NULL,
    "grade" FLOAT(53) NOT NULL,
    "story_points" FLOAT(53) NOT NULL,
    "created_at" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    "started_at" TIMESTAMP(0) WITHOUT TIME ZONE NULL,
    "ended_at" TIMESTAMP(0) WITHOUT TIME ZONE NULL,
    "paused_at" TIMESTAMP(0) WITHOUT TIME ZONE NULL,
    "finished_at" TIMESTAMP(0) WITHOUT TIME ZONE NULL
);
ALTER TABLE
    "tasks" ADD PRIMARY KEY("id");
COMMENT
ON COLUMN
    "tasks"."paused_at" IS 'Дата приостановки задачи';
COMMENT
ON COLUMN
    "tasks"."finished_at" IS 'Дата окончания задачи';
COMMENT
ON COLUMN
    "tasks"."parent_task_id" IS 'NULL для задач верхнего уровня (бывшие проекты)';

CREATE TABLE "users"(
    "id" BIGSERIAL NOT NULL,
    "slug" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "surname" VARCHAR(255) NOT NULL,
    "patronymic" VARCHAR(255) NULL,
    "password" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "bio" VARCHAR(500) NULL,
    "position" VARCHAR(255) NULL,
    "company" VARCHAR(255) NULL,
    "workplace" VARCHAR(255) NULL,
    "pronouns" VARCHAR(50) NULL,
    "url" VARCHAR(255) NULL,
    "role_id" BIGINT NOT NULL,
    "avatar_url" VARCHAR(255) NOT NULL,
    "confirmed" BOOLEAN NOT NULL DEFAULT '0',
    "created_at" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
ALTER TABLE
    "users" ADD PRIMARY KEY("id");
ALTER TABLE
    "users" ADD CONSTRAINT "users_slug_unique" UNIQUE("slug");
ALTER TABLE
    "users" ADD CONSTRAINT "users_email_unique" UNIQUE("email");
COMMENT
ON COLUMN
    "users"."role_id" IS 'Пользователь может иметь только одну роль';
COMMENT
ON COLUMN
    "users"."confirmed" IS 'Это подтверждено?';

CREATE TABLE "task_roles"(
    "id" BIGSERIAL NOT NULL,
    "slug" VARCHAR(255) NOT NULL,
    "task_id" BIGINT NOT NULL,
    "name" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "task_roles" ADD PRIMARY KEY("id");
CREATE INDEX "task_roles_slug_index" ON
    "task_roles"("slug");
COMMENT
ON COLUMN
    "task_roles"."slug" IS 'Служебное имя роли в задаче. Генерировать автоматически на основе name';

CREATE TABLE "task_role_permissions"(
    "id" BIGSERIAL NOT NULL,
    "task_role_id" BIGINT NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "permission" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "task_role_permissions" ADD PRIMARY KEY("id");
COMMENT
ON COLUMN
    "task_role_permissions"."name" IS 'Человеческое название разрешения';
COMMENT
ON COLUMN
    "task_role_permissions"."permission" IS 'Разрешение. Должно совпадать со значением на бэкенде';

CREATE TABLE "roles"(
    "id" BIGSERIAL NOT NULL,
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

-- Таблица для связи пользователей с задачами и их ролями (многие-ко-многим)
CREATE TABLE "task_user_roles"(
    "id" BIGSERIAL NOT NULL,
    "user_id" BIGINT NOT NULL,
    "task_id" BIGINT NOT NULL,
    "task_role_id" BIGINT NOT NULL,
    "created_at" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
ALTER TABLE
    "task_user_roles" ADD PRIMARY KEY("id");
ALTER TABLE
    "task_user_roles" ADD CONSTRAINT "task_user_roles_unique" UNIQUE("user_id", "task_id", "task_role_id");
COMMENT
ON COLUMN
    "task_user_roles"."task_role_id" IS 'Роль пользователя в конкретной задаче';

-- Добавляем роли: тимлид, менеджер, разработчик
INSERT INTO "roles" ("slug", "name") VALUES
    ('teamlead', 'Тимлид'),
    ('manager', 'Менеджер'),
    ('developer', 'Разработчик');

-- Внешние ключи
ALTER TABLE
    "tasks" ADD CONSTRAINT "tasks_parent_task_id_foreign" FOREIGN KEY("parent_task_id") REFERENCES "tasks"("id") ON DELETE CASCADE;
ALTER TABLE
    "tasks" ADD CONSTRAINT "tasks_creator_id_foreign" FOREIGN KEY("creator_id") REFERENCES "users"("id");
ALTER TABLE
    "users" ADD CONSTRAINT "users_role_id_foreign" FOREIGN KEY("role_id") REFERENCES "roles"("id");
ALTER TABLE
    "task_roles" ADD CONSTRAINT "task_roles_task_id_foreign" FOREIGN KEY("task_id") REFERENCES "tasks"("id") ON DELETE CASCADE;
ALTER TABLE
    "task_role_permissions" ADD CONSTRAINT "task_role_permissions_task_role_id_foreign" FOREIGN KEY("task_role_id") REFERENCES "task_roles"("id") ON DELETE CASCADE;
ALTER TABLE
    "task_user_roles" ADD CONSTRAINT "task_user_roles_user_id_foreign" FOREIGN KEY("user_id") REFERENCES "users"("id") ON DELETE CASCADE;
ALTER TABLE
    "task_user_roles" ADD CONSTRAINT "task_user_roles_task_id_foreign" FOREIGN KEY("task_id") REFERENCES "tasks"("id") ON DELETE CASCADE;
ALTER TABLE
    "task_user_roles" ADD CONSTRAINT "task_user_roles_task_role_id_foreign" FOREIGN KEY("task_role_id") REFERENCES "task_roles"("id") ON DELETE CASCADE;

-- Индексы для улучшения производительности
CREATE INDEX "tasks_parent_task_id_index" ON "tasks"("parent_task_id");
CREATE INDEX "tasks_creator_id_index" ON "tasks"("creator_id");
CREATE INDEX "task_roles_task_id_index" ON "task_roles"("task_id");
CREATE INDEX "task_user_roles_user_id_index" ON "task_user_roles"("user_id");
CREATE INDEX "task_user_roles_task_id_index" ON "task_user_roles"("task_id");
CREATE INDEX "task_user_roles_task_role_id_index" ON "task_user_roles"("task_role_id");
