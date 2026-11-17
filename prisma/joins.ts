/**
 * Prisma ORM & PostgreSQL Relational JOIN Operations
 * 
 * Demonstrates:
 * 1. Prisma Relation Joins (include / select eager loading via relational schema)
 * 2. Raw SQL JOIN queries (LEFT OUTER JOIN, INNER JOIN)
 * 3. Multi-table JOIN with Filtering, Grouping, and Ordering
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

/**
 * 1. Prisma ORM Eager Loading JOIN:
 * Queries alerts while joining with the associated Service record in a single operation.
 */
export async function getAlertsWithServiceRelation() {
  return await prisma.alert.findMany({
    where: {
      severity: "CRITICAL",
    },
    include: {
      serviceEntity: true, // SQL JOIN abstraction in Prisma ORM
    },
    orderBy: {
      createdAt: "desc",
    },
    take: 20,
  });
}

/**
 * 2. Raw SQL LEFT OUTER JOIN between alerts and services:
 */
export async function executeRawSqlJoin() {
  return await prisma.$queryRaw`
    SELECT 
      a.alert_id,
      a.service,
      a.severity,
      a.metric,
      a.metric_value,
      a.message,
      s.name AS service_name,
      s.status AS service_status,
      s.type AS service_type
    FROM alerts a
    LEFT JOIN services s ON a.service = s.service_id
    ORDER BY a.created_at DESC
    LIMIT 25;
  `;
}

/**
 * 3. SQL Relational JOIN with Orders and Order Items:
 */
export async function getOrdersWithItemsJoin() {
  return await prisma.order.findMany({
    include: {
      user: true,       // JOIN with users table
      items: {          // JOIN with order_items table
        include: {
          product: true // Nested JOIN with products table
        }
      }
    },
    orderBy: {
      createdAt: "desc",
    },
    take: 10,
  });
}

export default prisma;
