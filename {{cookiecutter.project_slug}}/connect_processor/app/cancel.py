from connect_processor.app.utils.utils import Utils, get_basic_value
from connect_processor.app.utils.globals import Globals

class Cancel():

    # This method processes the Fulfillment Requests in Pending status for cancel/terminate subscription action

    def process_request(request, client):
        # Type CANCEL means, it is a cancel request of an existing subscription in Connect

        # Get the subscription Id from the request that needs to be cancelled
        params = get_basic_value('asset', 'params')
        for param in params:
            param_type = get_basic_value(param, 'phase')
            # Here, the 'subscriptionId' is the id of fulfillment parameter
            if param_type == 'fulfillment' and get_basic_value(param, 'name') == 'subscriptionId':
                external_subscription_id = get_basic_value(param, 'value')
                # This external_subscription_id from Vendor platform might be required to call the Vendor API to cancel subscription

        # Cancel the subscription in vendor system by calling the Vendor API to cancel/terminate subscription
        # When successful, approve the fulfillment request

        # Provide the template id configured as Activation template. This template has the message for the customer that the subscription is terminated.
        payload = {"template_id": Globals.ACTIVATION_TEMPLATE}
        result = client.requests[get_basic_value(request, 'id')]('approve').post(payload=payload)
        # Returning the Activation Template will update the status of Fullfilment Request object to Approved and Subscription object status to Terminated.
        # The statuses will not get updated as Approved and Terminated if any of the mandatory/required fulfilment parameter in Fullfilment Request remain empty.






