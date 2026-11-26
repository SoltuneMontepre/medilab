import { SaleOrderLineListRenderer } from "@sale/js/sale_order_line_field/sale_order_line_field";
import { SaleOrderLineProductField } from "@sale/js/sale_product_field/sale_product_field";
import { patch } from "@web/core/utils/patch";

SaleOrderLineListRenderer.rowsTemplate = "sol_commerce.ListRenderer.Rows";

// Render each service package's parameter rows indented right below their package row.
patch(SaleOrderLineListRenderer.prototype, {
    isPackagePart(record) {
        return Boolean(record.data.linked_line_id?.id || record.data.linked_virtual_id);
    },

    getPackagePartRecords(record, records = this.props.list.records) {
        return records.filter((candidate) => {
            if (record.isNew) {
                return Boolean(
                    record.data.virtual_id && candidate.data.linked_virtual_id === record.data.virtual_id
                );
            }
            return candidate.data.linked_line_id?.id === record.resId;
        });
    },

    orderedRecords(list) {
        const records = list.records;
        const grouped = [];
        const placed = new Set();
        for (const record of records) {
            if (this.isPackagePart(record)) {
                continue;
            }
            grouped.push(record);
            placed.add(record);
            for (const part of this.getPackagePartRecords(record, records)) {
                grouped.push(part);
                placed.add(part);
            }
        }
        for (const record of records) {
            if (!placed.has(record)) {
                grouped.push(record);
            }
        }
        return grouped;
    },

    getRowClass(record) {
        let classNames = super.getRowClass(record);
        if (this.isPackagePart(record)) {
            classNames = `${classNames.replace("o_row_draggable", "")} o_medilab_package_part`;
        } else if (this.getPackagePartRecords(record).length > 0) {
            classNames = `${classNames} o_medilab_package_line`;
        }
        return classNames;
    },

    isFieldReadonly(column, record) {
        if (this.isPackagePart(record) && column.name !== "parameter_method_id") {
            return true;
        }
        return super.isFieldReadonly(column, record);
    },

    displayDeleteIcon(record) {
        return super.displayDeleteIcon(record) && !this.isPackagePart(record);
    },
});

patch(SaleOrderLineProductField.prototype, {
    _getOrderLines() {
        return this.props.record.model.root.data.product_line_ids || super._getOrderLines();
    },
});
