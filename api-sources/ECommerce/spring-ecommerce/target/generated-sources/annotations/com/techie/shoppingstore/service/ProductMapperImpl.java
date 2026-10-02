package com.techie.shoppingstore.service;

import com.techie.shoppingstore.dto.ProductDto;
import com.techie.shoppingstore.dto.ProductRatingDto;
import com.techie.shoppingstore.model.ElasticSearchProduct;
import com.techie.shoppingstore.model.Product;
import com.techie.shoppingstore.model.ProductAttribute;
import com.techie.shoppingstore.model.ProductRating;
import java.util.ArrayList;
import java.util.List;
import javax.annotation.Generated;
import org.springframework.stereotype.Component;

@Generated(
    value = "org.mapstruct.ap.MappingProcessor",
    date = "2026-01-28T21:17:46+0800",
    comments = "version: 1.3.0.Final, compiler: javac, environment: Java 1.8.0_462 (Amazon.com Inc.)"
)
@Component
public class ProductMapperImpl implements ProductMapper {

    @Override
    public ElasticSearchProduct productToESProduct(Product product) {
        if ( product == null ) {
            return null;
        }

        ElasticSearchProduct elasticSearchProduct = new ElasticSearchProduct();

        elasticSearchProduct.setId( product.getId() );
        elasticSearchProduct.setName( product.getName() );
        elasticSearchProduct.setDescription( product.getDescription() );
        elasticSearchProduct.setPrice( product.getPrice() );
        elasticSearchProduct.setSku( product.getSku() );
        elasticSearchProduct.setImageUrl( product.getImageUrl() );
        elasticSearchProduct.setCategory( product.getCategory() );
        List<ProductAttribute> list = product.getProductAttributeList();
        if ( list != null ) {
            elasticSearchProduct.setProductAttributeList( new ArrayList<ProductAttribute>( list ) );
        }
        elasticSearchProduct.setQuantity( product.getQuantity() );
        elasticSearchProduct.setManufacturer( product.getManufacturer() );
        elasticSearchProduct.setFeatured( product.isFeatured() );
        List<ProductRating> list1 = product.getProductRating();
        if ( list1 != null ) {
            elasticSearchProduct.setProductRating( new ArrayList<ProductRating>( list1 ) );
        }

        return elasticSearchProduct;
    }

    @Override
    public ProductDto mapESProductToDTO(ElasticSearchProduct elasticSearchProduct) {
        if ( elasticSearchProduct == null ) {
            return null;
        }

        ProductDto productDto = new ProductDto();

        productDto.setProductName( elasticSearchProduct.getName() );
        productDto.setImageUrl( elasticSearchProduct.getImageUrl() );
        productDto.setSku( elasticSearchProduct.getSku() );
        productDto.setPrice( elasticSearchProduct.getPrice() );
        productDto.setDescription( elasticSearchProduct.getDescription() );
        productDto.setManufacturer( elasticSearchProduct.getManufacturer() );
        productDto.setFeatured( elasticSearchProduct.isFeatured() );

        return productDto;
    }

    @Override
    public ProductRating mapProductRatingDto(ProductRatingDto productRatingDto) {
        if ( productRatingDto == null ) {
            return null;
        }

        ProductRating productRating = new ProductRating();

        productRating.setRatingStars( productRatingDto.getRatingStars() );
        productRating.setReview( productRatingDto.getReview() );
        productRating.setUserName( productRatingDto.getUserName() );

        return productRating;
    }

    @Override
    public ProductRatingDto mapProductRating(ProductRating productRating) {
        if ( productRating == null ) {
            return null;
        }

        ProductRatingDto productRatingDto = new ProductRatingDto();

        productRatingDto.setRatingId( productRating.getId() );
        productRatingDto.setRatingStars( productRating.getRatingStars() );
        productRatingDto.setReview( productRating.getReview() );
        productRatingDto.setUserName( productRating.getUserName() );

        return productRatingDto;
    }
}
