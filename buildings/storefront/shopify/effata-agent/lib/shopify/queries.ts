import { shopifyAdmin, ShopifyOrderNode } from "./client";

export const GET_RECENT_ORDERS = /* GraphQL */ `
  query GetRecentOrders($first: Int!) {
    orders(first: $first, sortKey: CREATED_AT, reverse: true) {
      edges {
        node {
          id
          name
          email
          totalPriceSet { shopMoney { amount currencyCode } }
          fulfillmentStatus
          financialStatus
          createdAt
          lineItems(first: 10) {
            edges {
              node {
                title
                quantity
                variant { id sku inventoryQuantity }
              }
            }
          }
        }
      }
    }
  }
`;

export const GET_PRODUCTS = /* GraphQL */ `
  query GetProducts($first: Int!) {
    products(first: $first) {
      edges {
        node {
          id
          title
          status
          descriptionHtml
          tags
          variants(first: 10) {
            edges {
              node { id sku price inventoryQuantity inventoryItem { id } }
            }
          }
          metafields(first: 5) {
            edges { node { namespace key value } }
          }
        }
      }
    }
  }
`;

export const UPDATE_PRODUCT = /* GraphQL */ `
  mutation UpdateProduct($input: ProductInput!) {
    productUpdate(input: $input) {
      product { id title descriptionHtml }
      userErrors { field message }
    }
  }
`;

export const CREATE_DISCOUNT = /* GraphQL */ `
  mutation CreateDiscount($basicCodeDiscount: DiscountCodeBasicInput!) {
    discountCodeBasicCreate(basicCodeDiscount: $basicCodeDiscount) {
      codeDiscountNode {
        id
        codeDiscount {
          ... on DiscountCodeBasic {
            title
            codes(first: 1) { edges { node { code } } }
          }
        }
      }
      userErrors { field message }
    }
  }
`;

export const ADJUST_INVENTORY = /* GraphQL */ `
  mutation AdjustInventory($input: InventoryAdjustQuantityInput!) {
    inventoryAdjustQuantity(input: $input) {
      inventoryLevel { available }
      userErrors { field message }
    }
  }
`;

export const SET_METAFIELD = /* GraphQL */ `
  mutation SetMetafield($metafields: [MetafieldsSetInput!]!) {
    metafieldsSet(metafields: $metafields) {
      metafields { id namespace key value }
      userErrors { field message }
    }
  }
`;

export async function getRecentOrders(first = 10): Promise<ShopifyOrderNode[]> {
  const data = await shopifyAdmin<{ orders: { edges: { node: ShopifyOrderNode }[] } }>(
    GET_RECENT_ORDERS,
    { first }
  );
  return data.orders.edges.map((e) => e.node);
}

export async function getLowStockProducts(threshold = 5) {
  const data = await shopifyAdmin<{
    products: {
      edges: {
        node: {
          id: string;
          title: string;
          variants: {
            edges: { node: { id: string; sku: string; inventoryQuantity: number } }[];
          };
        };
      }[];
    };
  }>(GET_PRODUCTS, { first: 100 });
  const out: { id: string; title: string; sku: string; quantity: number }[] = [];
  for (const e of data.products.edges) {
    for (const v of e.node.variants.edges) {
      if ((v.node.inventoryQuantity ?? 0) <= threshold) {
        out.push({
          id: e.node.id,
          title: e.node.title,
          sku: v.node.sku,
          quantity: v.node.inventoryQuantity ?? 0,
        });
      }
    }
  }
  return out;
}

export async function updateProduct(input: {
  id: string;
  title?: string;
  descriptionHtml?: string;
  tags?: string[];
}) {
  return shopifyAdmin(UPDATE_PRODUCT, { input });
}

export async function runShopifyQL(query: string) {
  return shopifyAdmin(query);
}
