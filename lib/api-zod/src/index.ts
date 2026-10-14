export * from "./generated/api";
export * from "./generated/types";

// Orval emits both a type and a validator with these query parameter names.
// Keep the type's established name and expose its validator with Schema suffix.
export type {
  AvailabilityApiV1CustomerAppGaragesGarageIdAvailabilityGetParams,
  ConversationMessagesApiV1CustomerAppConversationsConversationIdMessagesGetParams,
  PaymentAttemptsApiV1CustomerAppInvoicesInvoiceIdPaymentAttemptsGetParams,
  TicketMessagesApiV1CustomerAppSupportTicketsTicketIdMessagesGetParams,
  VehicleHistoryApiV1CustomerAppVehiclesVehicleIdServiceHistoryGetParams,
} from "./generated/types";
export {
  AvailabilityApiV1CustomerAppGaragesGarageIdAvailabilityGetParams as AvailabilityQuerySchema,
  ConversationMessagesApiV1CustomerAppConversationsConversationIdMessagesGetParams as ConversationMessagesQuerySchema,
  PaymentAttemptsApiV1CustomerAppInvoicesInvoiceIdPaymentAttemptsGetParams as PaymentAttemptsQuerySchema,
  TicketMessagesApiV1CustomerAppSupportTicketsTicketIdMessagesGetParams as TicketMessagesQuerySchema,
  VehicleHistoryApiV1CustomerAppVehiclesVehicleIdServiceHistoryGetParams as VehicleHistoryQuerySchema,
} from "./generated/api";
