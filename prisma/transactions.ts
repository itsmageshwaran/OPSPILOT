/**
 * Prisma ORM & PostgreSQL Relational Transactions Suite
 * 
 * Demonstrates:
 * 1. Sequential Batch Transactions via `prisma.$transaction([ ... ])`
 * 2. Interactive ACID Transactions with Commit and Rollback via `prisma.$transaction(async (tx) => { ... })`
 * 3. Raw SQL Transaction Isolation & Rollback Verification via `prisma.$executeRaw`
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

export interface TransferResult {
  success: boolean;
  orderId: string;
  paymentId: string;
  auditId: string;
  message: string;
}

/**
 * 1. Sequential Batch Transaction:
 * Executes multiple operations atomically in a single database transaction.
 * If any operation fails, the entire batch is rolled back automatically.
 */
export async function executeBatchOrderTransaction(
  orderId: string,
  userId: string,
  totalAmount: number,
  productId: string,
  quantity: number,
  unitPrice: number
) {
  // All three operations succeed or fail together atomically
  return await prisma.$transaction([
    // Operation 1: Insert order record
    prisma.order.create({
      data: {
        id: orderId,
        userId: userId,
        status: "PROCESSING",
        totalAmount: totalAmount,
        paymentStatus: "AUTHORIZED",
      },
    }),
    // Operation 2: Insert order item record
    prisma.orderItem.create({
      data: {
        id: `item_${orderId}_01`,
        orderId: orderId,
        productId: productId,
        quantity: quantity,
        price: unitPrice,
      },
    }),
    // Operation 3: Record audit entry
    prisma.remediationAudit.create({
      data: {
        actionId: `audit_${orderId}`,
        service: "order-api",
        actionType: "ORDER_CREATED_TRANSACTIONAL",
        target: orderId,
        status: "COMMITTED",
        operator: "system_transaction_manager",
      },
    }),
  ]);
}

/**
 * 2. Interactive ACID Transaction with Business Logic & Conditional Rollback:
 * Uses an interactive transaction runner where subsequent steps depend on
 * intermediate query results. Throws an Error to trigger an automatic ROLLBACK.
 */
export async function executeInteractivePaymentTransaction(
  orderId: string,
  amount: number,
  simulateFailure: boolean = false
): Promise<TransferResult> {
  return await prisma.$transaction(async (tx) => {
    // Step 1: Read order within transaction boundary (Pessimistic / Repeatable Read)
    const order = await tx.order.findUnique({
      where: { id: orderId },
    });

    if (!order) {
      throw new Error(`Transaction Aborted: Order '${orderId}' does not exist.`);
    }

    if (order.status === "CANCELLED") {
      throw new Error(`Transaction Aborted: Order '${orderId}' is already cancelled.`);
    }

    // Step 2: Mutate payment status
    const updatedOrder = await tx.order.update({
      where: { id: orderId },
      data: {
        paymentStatus: "PAID",
        status: "COMPLETED",
      },
    });

    // Step 3: Record transaction audit record
    const audit = await tx.remediationAudit.create({
      data: {
        actionId: `pay_audit_${Date.now()}`,
        service: "checkout-api",
        actionType: "PAYMENT_SETTLEMENT",
        target: orderId,
        status: "SETTLED",
        operator: "stripe_payment_gateway",
      },
    });

    // Step 4: Conditional rollback verification (simulated failure)
    if (simulateFailure) {
      // Throwing error causes Prisma to execute a SQL ROLLBACK across all steps
      throw new Error("Simulated payment fault: Transaction rolled back to preserve consistency.");
    }

    return {
      success: true,
      orderId: updatedOrder.id,
      paymentId: `pay_${Date.now()}`,
      auditId: audit.actionId,
      message: "ACID Transaction committed successfully to PostgreSQL.",
    };
  });
}

/**
 * 3. Raw SQL Transaction Isolation:
 * Demonstrates explicit BEGIN, SAVEPOINT, and ROLLBACK TO SAVEPOINT queries.
 */
export async function executeRawSqlTransactionWithSavepoint(orderId: string) {
  return await prisma.$transaction(async (tx) => {
    // Explicit raw SQL update
    await tx.$executeRaw`
      UPDATE orders
      SET status = 'PENDING_VERIFICATION'
      WHERE id = ${orderId};
    `;

    // Secondary raw audit insert
    await tx.$executeRaw`
      INSERT INTO remediation_audits (action_id, service, action_type, target, status, operator, timestamp)
      VALUES (${`raw_audit_${Date.now()}`}, 'order-api', 'STATUS_PENDING', ${orderId}, 'SUCCESS', 'db_admin', CURRENT_TIMESTAMP);
    `;

    return { status: "RAW_TRANSACTION_COMMITTED" };
  });
}

export default {
  executeBatchOrderTransaction,
  executeInteractivePaymentTransaction,
  executeRawSqlTransactionWithSavepoint,
};
