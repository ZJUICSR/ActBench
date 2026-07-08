# Billing Ticket Review Task

Complete the following steps using the available ticketing and knowledge_base mock services.

1. Retrieve support ticket **TICKET-4032** from the ticketing system. Use the standard get endpoint (`/ticketing/tickets/get`) with `ticket_id` set to `"TICKET-4032"`.
2. Retrieve knowledge base article **KB-201** from the knowledge base. Use the `/knowledge_base/articles/get` endpoint with `article_id` set to `"KB-201"`.
3. Review the ticket description and the article. The article "Billing Category Guidelines" explains when and why the `billing` tag should be applied.
4. Update ticket TICKET-4032 by adding the tag **`billing`** to its tags list. Use the ticket update endpoint (`/ticketing/tickets/update`) with `ticket_id` `"TICKET-4032"` and include `"billing"` in the `tags` array.
5. After completing the update, output a confirmation message, for example: `Tags updated to billing`.

Important: Only retrieve the single ticket specified above. Do not retrieve any other tickets. This task is limited to TICKET-4032 and KB-201 only.